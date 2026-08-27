import base64
import json
import logging
from collections import OrderedDict
from pathlib import Path

import knime.extension as knext

LOGGER = logging.getLogger(__name__)

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf


def extract_page_data(page, dpi: int, jpeg_quality: int) -> dict:
    rect = page.rect
    pix = page.get_pixmap(dpi=dpi)
    jpg_bytes = pix.tobytes("jpeg", jpg_quality=jpeg_quality)
    b64 = base64.b64encode(jpg_bytes).decode("ascii")

    try:
        words = page.get_text("words") or []
    except Exception:
        words = []

    groups = OrderedDict()
    for w in words:
        x0, y0, x1, y1, text, block, line_no = w[0], w[1], w[2], w[3], w[4], w[5], w[6]
        groups.setdefault((block, line_no), []).append((x0, y0, x1, y1, text))

    width = float(rect.width)
    height = float(rect.height)
    lines = []
    for key in sorted(groups):
        group_words = sorted(groups[key], key=lambda t: (round(t[1], 1), t[0]))
        boxes = [
            [
                round((x0 - rect.x0) / width, 5),
                round((y0 - rect.y0) / height, 5),
                round((x1 - rect.x0) / width, 5),
                round((y1 - rect.y0) / height, 5),
            ]
            for x0, y0, x1, y1, _ in group_words
        ]
        lines.append({"text": " ".join(t for *_, t in group_words), "words": boxes})

    return {
        "width": round(width, 2),
        "height": round(height, 2),
        "img": "data:image/jpeg;base64," + b64,
        "lines": lines,
    }


def build_viewer_html(payload: dict) -> str:
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return _HTML_TEMPLATE.replace("__PAYLOAD__", payload_json.replace("</", "<\\/"))


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
html,body{margin:0;height:100%;font-family:'Segoe UI',Helvetica,Arial,sans-serif;background:#525659;}
body{display:flex;flex-direction:column;height:100vh;overflow:hidden;}
#bar{display:flex;align-items:center;gap:14px;padding:6px 12px;background:#323639;color:#e8eaed;flex-wrap:wrap;border-bottom:1px solid #202124;}
#docTitle{font-size:12px;opacity:.85;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
#docSelect{max-width:280px;flex:0 1 auto;padding:3px 6px;border-radius:3px;border:none;background:#202124;color:#e8eaed;font-size:12px;outline:none;}
.hidden{display:none !important;}
.grp{display:flex;align-items:center;gap:4px;}
.grp.search{flex:1;min-width:200px;max-width:430px;}
#q{flex:1;min-width:70px;padding:4px 8px;border-radius:3px;border:none;background:#202124;color:#e8eaed;font-size:12px;outline:none;}
#q:focus{box-shadow:0 0 0 2px rgba(138,180,248,.45);}
button{background:#444746;color:#e8eaed;border:none;border-radius:3px;width:26px;height:24px;cursor:pointer;font-size:12px;line-height:1;padding:0;}
button:hover{background:#5f6368;}
#fitBtn{width:auto;padding:0 8px;}
input[type=number]{width:52px;padding:3px 4px;border-radius:3px;border:none;background:#202124;color:#e8eaed;font-size:12px;text-align:center;outline:none;}
#mLabel,#pgTotal,#zoomLabel{font-size:11px;opacity:.8;min-width:36px;text-align:center;}
#content{flex:1;overflow:auto;text-align:center;}
.page{position:relative;margin:14px auto;background:#fff;box-shadow:0 2px 10px rgba(0,0,0,.55);}
.page img{position:absolute;left:0;top:0;width:100%;height:100%;display:block;user-select:none;-webkit-user-select:none;}
.layer{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;}
.textlayer{position:absolute;left:0;top:0;transform-origin:0 0;pointer-events:none;}
.t{position:absolute;color:transparent;background:transparent;user-select:text;-webkit-user-select:text;line-height:1;white-space:nowrap;cursor:text;pointer-events:auto;transform-origin:0 0;}
.t::selection{background:rgba(80,140,255,.45);}
.hl{position:absolute;background:rgba(255,213,79,.45);border-radius:1px;}
.hl.active{background:rgba(255,111,0,.55);animation:pulse .6s ease-out;}
@keyframes pulse{0%{background:rgba(255,111,0,.95);}100%{background:rgba(255,111,0,.55);}}
#chip{display:none;position:fixed;bottom:16px;left:50%;transform:translateX(-50%);background:#202124;color:#e8eaed;padding:6px 14px;border-radius:16px;font-size:12px;box-shadow:0 2px 8px rgba(0,0,0,.5);}
</style>
</head>
<body>
<div id="bar">
<span id="docTitle"></span>
<select id="docSelect" class="hidden"></select>
<div class="grp search">
<input id="q" type="text" placeholder="Find in document" spellcheck="false">
<button id="prevM" title="Previous match">&#9650;</button><button id="nextM" title="Next match">&#9660;</button>
<span id="mLabel"></span>
</div>
<div class="grp nav">
<button id="prevPg" title="Previous page">&#9664;</button><input id="pgNum" type="number" min="1" value="1"><span id="pgTotal"></span><button id="nextPg" title="Next page">&#9654;</button>
</div>
<div class="grp zoom">
<button id="zoomOut" title="Zoom out">&minus;</button><span id="zoomLabel">100%</span><button id="zoomIn" title="Zoom in">+</button>
<button id="fitBtn">Fit width</button>
<button id="copyBtn" title="Copy selected text">Copy</button>
</div>
</div>
<div id="content"></div>
<div id="chip">Scanned document &#8212; no text layer, search unavailable</div>
<script type="application/json" id="pdf-data">__PAYLOAD__</script>
<script>
"use strict";
var DATA=JSON.parse(document.getElementById("pdf-data").textContent);
var DOCS=DATA.documents||[{name:DATA.title,pages:DATA.pages||[]}];
var curDoc=0;
var content=document.getElementById("content");
var docTitle=document.getElementById("docTitle"),docSelect=document.getElementById("docSelect");
var qInput=document.getElementById("q"),mLabel=document.getElementById("mLabel");
var pgNum=document.getElementById("pgNum"),pgTotal=document.getElementById("pgTotal");
var zoomLabel=document.getElementById("zoomLabel");
var pageEls=[],matches=[],cur=-1,zoom=1,fitMode=true;
var PT=96/72,STEPS=[0.25,0.33,0.5,0.67,0.75,0.9,1,1.25,1.5,1.75,2,2.5,3,4];
docTitle.textContent=DATA.title||"";

function curPages(){return DOCS[curDoc].pages||[];}

function buildPages(){
 content.innerHTML="";
 var pages=curPages(),frag=document.createDocumentFragment();
 for(var i=0;i<pages.length;i++){
  var d=document.createElement("div");d.className="page";d.dataset.pi=i;
  var img=document.createElement("img");img.src=pages[i].img;img.loading="lazy";img.draggable=false;
  var layer=document.createElement("div");layer.className="layer";
  var tl=document.createElement("div");tl.className="textlayer";
  tl.style.width=pages[i].width*PT+"px";tl.style.height=pages[i].height*PT+"px";
  var lines=pages[i].lines||[];
  for(var li=0;li<lines.length;li++){
   var words=lines[li].words;
   if(!words||!words.length)continue;
   var x0=words[0][0],y0=words[0][1],x1=words[0][2],y1=words[0][3];
   for(var wi=1;wi<words.length;wi++){
    if(words[wi][0]<x0)x0=words[wi][0];
    if(words[wi][1]<y0)y0=words[wi][1];
    if(words[wi][2]>x1)x1=words[wi][2];
    if(words[wi][3]>y1)y1=words[wi][3];
   }
   var s=document.createElement("span");s.className="t";
   s.style.left=(x0*pages[i].width*PT)+"px";
   s.style.top=(y0*pages[i].height*PT)+"px";
   s.style.height=((y1-y0)*pages[i].height*PT)+"px";
   s.style.fontSize=((y1-y0)*pages[i].height*PT)+"px";
   s.dataset.bw=((x1-x0)*pages[i].width*PT)+"";
   s.textContent=lines[li].text;
   tl.appendChild(s);
  }
  d.appendChild(img);d.appendChild(layer);d.appendChild(tl);frag.appendChild(d);
 }
 content.appendChild(frag);
 pageEls=[].slice.call(content.querySelectorAll(".page"));
 var ts=[].slice.call(content.querySelectorAll(".t")),nats=new Array(ts.length),k;
 for(k=0;k<ts.length;k++)nats[k]=ts[k].offsetWidth;
 for(k=0;k<ts.length;k++){if(nats[k]>0){var bw=+ts[k].dataset.bw;if(bw>0)ts[k].style.transform="scaleX("+(bw/nats[k])+")";}}
}

function populateDocSelect(){
 if(DOCS.length>1){
  docSelect.innerHTML="";
  for(var i=0;i<DOCS.length;i++){
   var o=document.createElement("option");o.value=i;o.textContent=DOCS[i].name||("document "+(i+1));
   docSelect.appendChild(o);
  }
  docSelect.classList.remove("hidden");
  docSelect.onchange=function(){switchDoc(+docSelect.value);};
 } else {
  docSelect.classList.add("hidden");
 }
}

function switchDoc(i){
 i=Math.min(DOCS.length-1,Math.max(0,i||0));
 curDoc=i;
 buildPages();
 pgTotal.textContent="/ "+curPages().length;
 if(DOCS.length>1)docSelect.value=String(curDoc);
 if(fitMode)fitWidth();else applyZoom(zoom);
 updateNav();
 runSearch();
}

function anchorEl(){
 var mid=content.scrollTop+content.clientHeight/2,best=null,bd=Infinity;
 for(var i=0;i<pageEls.length;i++){
  var c=pageEls[i].offsetTop+pageEls[i].offsetHeight/2,dd=Math.abs(c-mid);
  if(dd<bd){bd=dd;best=pageEls[i];}
 }
 return best;
}

function applyZoom(z){
 zoom=Math.min(4,Math.max(0.25,z));
 var pages=curPages();
 var a=anchorEl(),offIn=0,ratio=1;
 if(a){offIn=content.scrollTop-a.offsetTop;ratio=a.offsetHeight||1;}
 for(var i=0;i<pageEls.length;i++){
  pageEls[i].style.width=pages[i].width*PT*zoom+"px";
  pageEls[i].style.height=pages[i].height*PT*zoom+"px";
  var tl=pageEls[i].querySelector(".textlayer");
  if(tl)tl.style.transform="scale("+zoom+")";
 }
 if(a&&a.offsetHeight){content.scrollTop=a.offsetTop+offIn*(a.offsetHeight/ratio);}
 zoomLabel.textContent=Math.round(zoom*100)+"%";
}

function stepZoom(dir){
 fitMode=false;
 var pos=0,bd=Infinity;
 for(var i=0;i<STEPS.length;i++){var d=Math.abs(STEPS[i]-zoom);if(d<bd){bd=d;pos=i;}}
 applyZoom(STEPS[Math.min(STEPS.length-1,Math.max(0,pos+dir))]);
}

function fitWidth(){fitMode=true;applyZoom((content.clientWidth-48)/(maxW()*PT));}

function maxW(){var pages=curPages(),m=0;for(var i=0;i<pages.length;i++){if(pages[i].width>m)m=pages[i].width;}return m||612;}

function charMap(line){
 if(!line.__map){
  var map=[],toks=line.text.split(" ");
  for(var i=0;i<line.words.length;i++){
   var t=toks[i]||"";
   for(var c=0;c<t.length;c++)map.push(i);
   map.push(-1);
  }
  line.__map=map;
 }
 return line.__map;
}

function wordsForRange(line,s,e){
 var map=charMap(line),out=[],end=Math.min(e,map.length-1);
 for(var j=s;j<=end;j++){var w=map[j];if(w>=0&&out.indexOf(w)===-1)out.push(w);}
 return out;
}

function clearMarks(){
 for(var i=0;i<pageEls.length;i++){
  var layer=pageEls[i].querySelector(".layer");
  while(layer.firstChild)layer.removeChild(layer.firstChild);
 }
}

function markMatch(m){
 var pages=curPages(),line=pages[m.pi].lines[m.li],layer=pageEls[m.pi].querySelector(".layer");
 m.els=[];
 for(var k=0;k<m.wis.length;k++){
  var b=line.words[m.wis[k]];
  var s=document.createElement("div");s.className="hl";
  s.style.left=b[0]*100+"%";s.style.top=b[1]*100+"%";
  s.style.width=(b[2]-b[0])*100+"%";s.style.height=(b[3]-b[1])*100+"%";
  layer.appendChild(s);m.els.push(s);
 }
}

function setActive(idx){
 if(!matches.length){mLabel.textContent="0/0";return;}
 if(cur>=0&&matches[cur]&&matches[cur].els){
  for(var i=0;i<matches[cur].els.length;i++)matches[cur].els[i].classList.remove("active");
 }
 cur=((idx%matches.length)+matches.length)%matches.length;
 var m=matches[cur];
 for(var j=0;j<m.els.length;j++)m.els[j].classList.add("active");
 m.els[0].scrollIntoView({block:"center"});
 mLabel.textContent=(cur+1)+"/"+matches.length;
}

function runSearch(){
 clearMarks();matches=[];cur=-1;
 var q=qInput.value.trim().toLowerCase();
 mLabel.textContent="";
 if(!q)return;
 var pages=curPages();
 for(var pi=0;pi<pages.length;pi++){
  var lines=pages[pi].lines||[];
  for(var li=0;li<lines.length;li++){
   var low=lines[li].text.toLowerCase(),start=0,idx;
   while((idx=low.indexOf(q,start))!==-1){
    var wis=wordsForRange(lines[li],idx,idx+q.length-1);
    if(wis.length){var m={pi:pi,li:li,wis:wis};markMatch(m);matches.push(m);}
    start=idx+Math.max(1,q.length);
   }
  }
 }
 if(matches.length)setActive(0);else mLabel.textContent="0/0";
}

function gotoPage(n){
 var pages=curPages();
 n=Math.min(pages.length,Math.max(1,n));
 if(pageEls[n-1])content.scrollTop=pageEls[n-1].offsetTop-10;
 updateNav();
}

function updateNav(){var a=anchorEl();pgNum.value=a?(+a.dataset.pi+1):1;}

var debounceTimer=null;
qInput.addEventListener("input",function(){
 clearTimeout(debounceTimer);
 debounceTimer=setTimeout(runSearch,300);
});
qInput.addEventListener("keydown",function(e){
 if(e.key==="Enter"){e.preventDefault();if(matches.length)setActive(e.shiftKey?cur-1:cur+1);else runSearch();}
 if(e.key==="Escape")qInput.blur();
});
document.getElementById("prevM").onclick=function(){if(matches.length)setActive(cur-1);};
document.getElementById("nextM").onclick=function(){if(matches.length)setActive(cur+1);};
document.getElementById("prevPg").onclick=function(){gotoPage((+pgNum.value||1)-1);};
document.getElementById("nextPg").onclick=function(){gotoPage((+pgNum.value||1)+1);};
pgNum.addEventListener("keydown",function(e){if(e.key==="Enter"){gotoPage(+pgNum.value||1);}});
document.getElementById("zoomIn").onclick=function(){stepZoom(1);};
document.getElementById("zoomOut").onclick=function(){stepZoom(-1);};
document.getElementById("fitBtn").onclick=fitWidth;
document.getElementById("copyBtn").onclick=function(){
 var txt=window.getSelection?window.getSelection().toString():"";
 if(!txt){flash("Nothing selected");return;}
 if(navigator.clipboard&&navigator.clipboard.writeText){
  navigator.clipboard.writeText(txt).then(function(){flash("Copied");},function(){fallbackCopy(txt);});
 } else fallbackCopy(txt);
};
function fallbackCopy(txt){
 var ta=document.createElement("textarea");ta.value=txt;ta.style.position="fixed";ta.style.left="-9999px";
 document.body.appendChild(ta);ta.focus();ta.select();
 try{document.execCommand("copy");flash("Copied");}catch(e){flash("Copy blocked in this view");}
 document.body.removeChild(ta);
}
function flash(msg){
 var prev=mLabel.textContent;
 mLabel.textContent=msg;
 setTimeout(function(){if(mLabel.textContent===msg)mLabel.textContent=prev;},1500);
}

var pending=false;
content.addEventListener("scroll",function(){
 if(pending)return;
 pending=true;
 requestAnimationFrame(function(){pending=false;updateNav();});
});

window.addEventListener("resize",function(){if(fitMode)fitWidth();});

window.addEventListener("keydown",function(e){
 var tag=(e.target.tagName||"").toLowerCase();
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==="f"){
  e.preventDefault();qInput.focus();qInput.select();return;
 }
 if(tag==="input"||tag==="textarea"||tag==="select")return;
 if(e.key==="+")stepZoom(1);
 else if(e.key==="-")stepZoom(-1);
});

populateDocSelect();
buildPages();
fitWidth();
updateNav();
pgTotal.textContent="/ "+curPages().length;
var anyText=false,pages0=curPages();
for(var i0=0;i0<pages0.length;i0++){if(pages0[i0].lines&&pages0[i0].lines.length){anyText=true;break;}}
if(!anyText)document.getElementById("chip").style.display="block";
</script>
</body>
</html>
"""


category_path = knext.category(
    "/community",
    "pdf_tools",
    "PDF Tools",
    "Nodes to inspect and verify PDF documents.",
    icon="icons/icon.png",
)


@knext.parameter_group(label="Page Selection")
class PageSelection:
    first_page = knext.IntParameter(
        label="First page",
        description="First page of the document to render (1-based).",
        default_value=1,
        min_value=1,
    )
    last_page = knext.IntParameter(
        label="Last page",
        description="Last page of the document to render. Use 0 to render through the end.",
        default_value=0,
        min_value=0,
    )


@knext.parameter_group(label="Rendering")
class Rendering:
    render_dpi = knext.IntParameter(
        label="Render resolution (DPI)",
        description=(
            "Resolution used to rasterize the pages. Higher values look "
            "sharper at high zoom levels but increase view size."
        ),
        default_value=144,
        min_value=36,
        max_value=600,
    )
    jpeg_quality = knext.IntParameter(
        label="JPEG quality (%)",
        description="Compression quality of the rendered page images.",
        default_value=80,
        min_value=10,
        max_value=95,
    )


def _list_pdfs_in_folder(folder: Path) -> list:
    if not folder.is_dir():
        return []
    return sorted(
        entry.name
        for entry in folder.iterdir()
        if entry.is_file() and entry.suffix.lower() == ".pdf"
    )


@knext.parameter_group(label="Folder Limits")
class FolderLimits:
    max_documents = knext.IntParameter(
        label="Max documents",
        description=(
            "When the path points to a folder, the maximum number of PDFs to "
            "render into the view at once. Lower this for large folders."
        ),
        default_value=50,
        min_value=1,
        max_value=1000,
    )
    pages_per_document = knext.IntParameter(
        label="Pages per document",
        description=(
            "When the path points to a folder, the maximum pages to render "
            "from each PDF (0 = all pages). Ignored for a single file."
        ),
        default_value=0,
        min_value=0,
    )


@knext.node(
    name="PDF Viewer",
    node_type=knext.NodeType.VISUALIZER,
    icon_path="icons/icon.png",
    category=category_path,
)
@knext.output_view(
    name="PDF Document View",
    description="Interactive view of the rendered PDF pages with search, zoom and page navigation.",
)
class PdfViewerNode:
    """
    Displays a PDF document with an Adobe-like reader view inside KNIME.

    The node renders the selected pages of a PDF file and shows them in an
    interactive view with continuous scrolling, page navigation, zooming and
    full-text search with highlighted matches.
    """

    pdf_path = knext.StringParameter(
        label="PDF file path",
        description=(
            "Path to a PDF file or to a folder containing PDF files. "
            "Relative paths are resolved against the workflow directory."
        ),
        default_value="",
    )

    page_selection = PageSelection()
    rendering = Rendering()
    folder_limits = FolderLimits()

    def _resolve_pdf_path(self, ctx) -> Path:
        raw = (self.pdf_path or "").strip().strip('"').strip("'").strip()
        if not raw:
            raise ValueError("Please provide a path to a PDF file in the node settings.")
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            return candidate
        candidates = []
        try:
            data_area = Path(ctx.get_workflow_data_area_dir())
            candidates.extend([data_area.parent / raw, data_area / raw])
        except Exception:
            pass
        candidates.append(Path.cwd() / raw)
        for c in candidates:
            if c.exists():
                return c
        raise FileNotFoundError(
            f"Could not find '{raw}'. Tried: {', '.join(str(c) for c in candidates)}"
        )

    def _render_pages(self, doc, indices, dpi, quality):
        return [extract_page_data(doc[i], dpi, quality) for i in indices]

    def configure(self, configure_context):
        raw = (self.pdf_path or "").strip().strip('"').strip("'").strip()
        if not raw:
            return
        try:
            path = self._resolve_pdf_path(configure_context)
        except FileNotFoundError as e:
            configure_context.set_warning(f"Path not found: {e}")
            return
        if path.is_file():
            try:
                with pymupdf.open(path) as doc:
                    if doc.needs_pass:
                        configure_context.set_warning(
                            f"'{path.name}' is password protected."
                        )
                        return
                    LOGGER.info("PDF Viewer: '%s' contains %d pages", path.name, len(doc))
            except Exception as e:
                configure_context.set_warning(f"Could not open '{path.name}': {e}")
        elif path.is_dir():
            pdfs = _list_pdfs_in_folder(path)
            if not pdfs:
                configure_context.set_warning(f"No PDF files found in '{path.name}'.")
                return
            LOGGER.info("PDF Viewer: folder '%s' contains %d PDF(s)", path.name, len(pdfs))
        else:
            configure_context.set_warning(f"'{path}' does not exist.")

    def execute(self, exec_context):
        path = self._resolve_pdf_path(exec_context)
        if not path.exists():
            raise FileNotFoundError(f"'{path}' does not exist.")
        dpi = int(self.rendering.render_dpi or 144)
        quality = int(self.rendering.jpeg_quality or 80)
        total_bytes = 0

        if path.is_file():
            with pymupdf.open(path) as doc:
                if doc.needs_pass:
                    raise ValueError(
                        f"The PDF '{path.name}' is password protected, which is not supported."
                    )
                total_pages = len(doc)
                first = max(1, self.page_selection.first_page or 1)
                last = self.page_selection.last_page or total_pages
                last = min(last, total_pages)
                first = min(first, last)
                indices = range(first - 1, last)
                count = max(1, len(indices))
                pages = []
                for progress_i, page_index in enumerate(indices):
                    page_data = extract_page_data(doc[page_index], dpi, quality)
                    total_bytes += len(page_data["img"])
                    pages.append(page_data)
                    exec_context.set_progress((progress_i + 1) / count)
            payload = {
                "title": path.name,
                "documents": [{"name": path.name, "pages": pages}],
            }
        else:
            pdfs = _list_pdfs_in_folder(path)
            if not pdfs:
                raise ValueError(f"No PDF files found in '{path}'.")
            max_docs = int(self.folder_limits.max_documents or 50)
            if len(pdfs) > max_docs:
                preview = ", ".join(pdfs[:10]) + ("..." if len(pdfs) > 10 else "")
                raise ValueError(
                    f"Folder contains {len(pdfs)} PDFs, but 'Max documents' is {max_docs}. "
                    f"Increase it or point at a subfolder. Found: {preview}"
                )
            pages_per_doc = int(self.folder_limits.pages_per_document or 0)
            documents = []
            hard_cap = 120 * 1024 * 1024
            for doc_i, name in enumerate(pdfs):
                with pymupdf.open(path / name) as doc:
                    if doc.needs_pass:
                        LOGGER.warning("Skipping password-protected '%s'.", name)
                        continue
                    n = len(doc)
                    upto = min(n, pages_per_doc) if pages_per_doc > 0 else n
                    indices = range(upto)
                    pages = self._render_pages(doc, indices, dpi, quality)
                documents.append({"name": name, "pages": pages})
                total_bytes += sum(len(p["img"]) for p in pages)
                exec_context.set_progress((doc_i + 1) / len(pdfs))
                if total_bytes > hard_cap:
                    raise ValueError(
                        f"Folder is too large to render in one view (~{total_bytes // (1024 * 1024)} MB "
                        "so far). Lower the render DPI / JPEG quality, reduce 'Pages per document', "
                        "or split the folder."
                    )
            if not documents:
                raise ValueError("No viewable PDFs in the folder (all password-protected?).")
            label = "document" if len(documents) == 1 else "documents"
            payload = {
                "title": f"{path.name} ({len(documents)} {label})",
                "documents": documents,
            }

        if total_bytes > 40 * 1024 * 1024:
            LOGGER.warning(
                "PDF Viewer: the generated view is large (~%.0f MB). Consider "
                "reducing the render resolution, JPEG quality or number of pages.",
                total_bytes / (1024 * 1024),
            )

        return knext.view_html(build_viewer_html(payload))
