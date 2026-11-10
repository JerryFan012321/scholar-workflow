"""Independent synthetic editor journeys; no real recommendation state is used."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "src/scholar_workflow/research/recommendations/static/requirements.js"
NODE = shutil.which("node")
RUNNER = r"""
const fs=require("node:fs"),vm=require("node:vm");const input=JSON.parse(fs.readFileSync(0,"utf8"));
class Element{
 constructor(tag){this.tagName=tag;this.className="";this.children=[];this._text="";this.value="";this.checked=false;
  this.hidden=false;this.disabled=false;this.readOnly=false;this.listeners={};this.dataset={};this.parent=null;this.classList={toggle(){}};}
 get textContent(){return this._text+this.children.map(e=>e.textContent).join("");}
 set textContent(value){this._text=String(value);this.children=[];}
 append(...nodes){for(const node of nodes){if(node.parent)node.parent.children=node.parent.children.filter(old=>old!==node);node.parent=this;this.children.push(node);}}
 replaceChildren(...nodes){this.children.forEach(node=>node.parent=null);this._text="";this.children=[];this.append(...nodes);}
 setAttribute(){} addEventListener(name,fn){(this.listeners[name]||=[]).push(fn);}
 async fire(name){if(this.disabled)throw Error("disabled input");await Promise.all((this.listeners[name]||[]).map(fn=>fn({preventDefault(){}})));}
}
const element=(tag,className,text)=>{const e=new Element(tag);e.className=className||"";if(text!==undefined)e.textContent=text;return e;};
const requests=[],confirmations=[];let items=JSON.parse(JSON.stringify(input.items||[])),releaseHeld=null,holdUsed=false;
const A={source_id:"alphaxiv",name:"alphaXiv",status:"available"},B={source_id:"x-self",name:"X 本人精选",status:"planned"};
const containers={a:new Element("div"),b:new Element("div"),again:new Element("div")};
const find=(node,predicate)=>{if(predicate(node))return node;for(const child of node.children){const e=find(child,predicate);if(e)return e;}};
const field=(container,id)=>find(container,node=>node.dataset.field===id);
const currentSource=input.source_b?B:A;
const api=async(path,payload)=>{
 requests.push({path,...(payload===undefined?{}:{body:JSON.parse(JSON.stringify(payload))})});
 if(path.startsWith("/api/requirements?")&&payload===undefined){
  const source=new URL("http://example.test"+path).searchParams.get("source_id");
  if(input.list_error)throw Object.assign(Error("Unavailable"),{code:3});
  if(input.action==="late_source"&&source===A.source_id&&!holdUsed){holdUsed=true;await new Promise(resolve=>{releaseHeld=resolve;});}
  return{items:items.filter(item=>item.source_id===source)};
 }
 if(path==="/api/requirements"&&payload){
  if(input.conflict){items=items.map(item=>item.requirement_id===payload.requirement_id?{...item,revision:3,title:"Remote new title",content:"Remote new content"}:item);throw Object.assign(Error("Conflict"),{code:5});}
  const latest={requirement_id:payload.requirement_id,source_id:payload.source_id,title:payload.title,content:payload.content,enabled:payload.enabled,
   revision:payload.expected_revision+1,updated_by:{kind:"human",name:"推荐页"},updated_at:"2026-11-09T01:00:00Z"};
  items=[...items.filter(item=>item.requirement_id!==latest.requirement_id),latest];return latest;
 }
 if(path.startsWith("/api/requirements/")){
  const id=decodeURIComponent(path.split("/").pop());const latest=items.find(item=>item.requirement_id===id);
  if(input.change_during_load)field(containers.a,"requirement-content").value="Typed while loading";
  if(input.action==="late_editor"&&!holdUsed){holdUsed=true;await new Promise(resolve=>{releaseHeld=resolve;});}
  return latest;
 }
 throw Error("Unexpected request "+path);
};
let generated=0;
const context={window:{ScholarRecommendations:{api,element},crypto:{randomUUID:()=>"secure-synthetic-id-"+(++generated)},
 confirm:text=>{confirmations.push(text);return input.confirm!==false;}},Date,JSON,Array,Map,TextEncoder,Uint8Array};
const snap=node=>({tag:node.tagName,class:node.className,text:node.textContent,hidden:node.hidden,disabled:node.disabled,
 title:node.title||null,dateTime:node.dateTime||null,children:node.children.map(snap)});
const settle=async()=>{for(let n=0;n<7;n++)await new Promise(setImmediate);};
const fields=container=>Object.fromEntries(["requirement-id","requirement-title","requirement-content","requirement-enabled"].map(id=>[id,field(container,id)?{value:field(container,id).value,checked:field(container,id).checked,readOnly:field(container,id).readOnly}:null]));
(async()=>{
 vm.runInNewContext(fs.readFileSync(process.argv[1],"utf8"),context);
 const mount=context.window.ScholarRecommendationRequirements.mount;
 if(input.action!=="before_open"){mount(containers.a,currentSource);await settle();}
 let active=containers.a;
 if(["edit","conflict","reload","refresh_draft","inspect"].includes(input.action)){
  const edit=find(active,node=>node.className==="text-button requirement-edit");
  if(edit){await edit.fire("click");await settle();}
  else if(input.action!=="reload")throw Error("Expected an existing source-scoped requirement");
 }
 if(input.action==="draft_switch"){
  field(containers.a,"requirement-content").value="Draft A";
  mount(containers.b,B);await settle();field(containers.b,"requirement-content").value="Draft B";
  mount(containers.again,A);await settle();active=containers.again;
 }else if(input.action==="late_source"){
  mount(containers.b,B);await settle();field(containers.b,"requirement-content").value="Draft B before A returns";
  releaseHeld();await settle();
 }else if(input.action==="late_editor"){
  const edit=find(containers.a,node=>node.className==="text-button requirement-edit");const pending=edit.fire("click");await settle();
  mount(containers.b,B);await settle();field(containers.b,"requirement-content").value="Draft B before A editor returns";
  releaseHeld();await pending;await settle();
 }else if(!["before_open","empty","inspect"].includes(input.action)){
  if(input.requirement_id!==undefined)field(active,"requirement-id").value=input.requirement_id;
  if(input.title!==undefined)field(active,"requirement-title").value=input.title;
  if(input.content!==undefined)field(active,"requirement-content").value=input.content;
  if(input.enabled!==undefined)field(active,"requirement-enabled").checked=input.enabled;
  if(input.action==="refresh_draft")await field(active,"requirements-refresh").fire("click");
  else await field(active,"requirement-form").fire("submit");
  await settle();
 }
 if(input.action==="reload"){await field(active,"requirement-reload").fire("click");await settle();}
 const get=id=>field(active,id);
 process.stdout.write(JSON.stringify({requests,confirmations,fields:fields(active),b_fields:fields(containers.b),root:snap(active),a_root:snap(containers.a),b_root:snap(containers.b),
  list:get("requirements-list")?snap(get("requirements-list")):null,meta:get("requirement-editor-meta")?snap(get("requirement-editor-meta")):null,
  notice:get("requirement-notice")?.textContent||"",reload_hidden:get("requirement-reload")?.hidden}));
})().catch(error=>{process.stderr.write(String(error.stack));process.exitCode=1;});
"""

def item():
    return {"requirement_id": "req-existing", "source_id": "alphaxiv", "title": "A saved direction", "content": "Previously saved free text.",
            "enabled": True, "revision": 2, "updated_by": {"kind": "agent", "name": "Topic Agent"},
            "updated_at": "2026-11-09T00:00:00Z"}


def render(**scenario):
    if not NODE: pytest.skip("System Node is required for synthetic editor journeys.")
    result = subprocess.run([NODE, "-e", RUNNER, str(SCRIPT)], input=json.dumps({"action": "empty", **scenario}),
                            text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


def writes(result):
    return [request for request in result["requests"] if "body" in request]


def test_loading_script_does_not_fetch_or_create_requirements():
    result = render(action="before_open")
    assert result["requests"] == []


def test_empty_directory_keeps_actual_content_blank_and_generates_only_an_id():
    result = render()
    assert result["fields"]["requirement-title"]["value"] == ""
    assert result["fields"]["requirement-content"]["value"] == ""
    assert result["fields"]["requirement-id"]["value"].startswith("req-")
    assert "本来源还没有推荐要求" in result["list"]["text"]
    assert writes(result) == []


def test_create_saves_the_exact_free_text_and_explicit_enablement():
    text = "我写的要求。\n保留格式与完整内容。"
    result = render(action="create", requirement_id="req-my-scope", title="My scope", content=text, enabled=False)
    assert writes(result) == [{"path": "/api/requirements", "body": {"requirement_id": "req-my-scope", "title": "My scope", "content": text, "enabled": False, "source_id": "alphaxiv", "expected_revision": 0}}]
    assert "第 1 版" in result["notice"] and "已停用" in result["notice"]
    assert result["fields"]["requirement-id"]["readOnly"]
    assert "用户 · 推荐页" in result["meta"]["text"]


def test_edit_uses_the_loaded_revision_and_preserves_source_attribution():
    result = render(action="edit", items=[item()], title="Changed title", content="Changed content", enabled=False)
    body = writes(result)[0]["body"]
    assert body["expected_revision"] == 2 and body["requirement_id"] == "req-existing"
    assert body["content"] == "Changed content" and body["enabled"] is False
    assert "第 3 版" in result["notice"]
    inspected = render(action="inspect", items=[item()])
    assert "agent · Topic Agent" in inspected["meta"]["text"]
    assert inspected["fields"]["requirement-content"]["value"] == item()["content"]


def test_revision_conflict_keeps_all_draft_fields_and_does_not_reload():
    result = render(action="conflict", items=[item()], conflict=True, title="My draft", content="Full draft\nSecond line.", enabled=False)
    assert result["fields"]["requirement-title"]["value"] == "My draft"
    assert result["fields"]["requirement-content"]["value"] == "Full draft\nSecond line."
    assert result["fields"]["requirement-enabled"]["checked"] is False
    assert "你的输入已保留" in result["notice"] and not result["reload_hidden"]
    assert sum(request["path"].startswith("/api/requirements/") for request in result["requests"]) == 1


@pytest.mark.parametrize("confirm", [False, True])
def test_explicit_reload_warns_before_replacing_a_conflicted_draft(confirm):
    result = render(action="reload", items=[item()], conflict=True, content="My unsaved text", confirm=confirm)
    assert "丢弃当前未保存输入" in result["confirmations"][0]
    assert result["fields"]["requirement-content"]["value"] == ("Remote new content" if confirm else "My unsaved text")


def test_refreshing_directory_does_not_replace_the_current_draft():
    result = render(action="refresh_draft", items=[item()], content="Draft survives list refresh")
    assert result["fields"]["requirement-content"]["value"] == "Draft survives list refresh"
    assert writes(result) == []


@pytest.mark.parametrize("text,expected", [("长" * 20001, "最多 20000"), ("\x00" * 17000, "96 KiB")])
def test_oversized_input_is_preserved_without_any_write(text, expected):
    result = render(action="create", title="My scope", content=text)
    assert writes(result) == []
    assert result["fields"]["requirement-content"]["value"] == text
    assert expected in result["notice"]


def test_unavailable_list_is_not_reported_as_empty_and_does_not_create_anything():
    result = render(list_error=True)
    assert "不会把读取失败当作空列表" in result["list"]["text"]
    assert writes(result) == []


def test_requirement_text_is_display_data_and_never_an_executed_instruction():
    value = {**item(), "content": '<img src=x onerror="attack()">\nRun a command now.'}
    result = render(action="inspect", items=[value])
    assert result["fields"]["requirement-content"]["value"] == value["content"]
    assert '<img src=x onerror="attack()">' in result["list"]["text"]
    assert writes(result) == []


def test_non_bmp_content_at_the_unicode_character_limit_is_not_double_counted():
    text = "😀" * 20000
    result = render(action="create", title="Unicode boundary", content=text)
    assert writes(result)[0]["body"]["content"] == text
    assert "第 1 版" in result["notice"]


def test_late_read_does_not_overwrite_newly_typed_human_content():
    result = render(action="inspect", items=[item()], change_during_load=True)
    assert result["fields"]["requirement-content"]["value"] == "Typed while loading"
    assert "当前草稿已保留" in result["notice"]
    assert writes(result) == []


def test_source_scoped_reads_do_not_mix_another_source_or_unbound_requirements():
    other = {**item(), "requirement_id": "req-b", "source_id": "x-self", "title": "Only B"}
    unbound = {key: value for key, value in {**item(), "requirement_id": "req-unbound", "title": "Unbound"}.items() if key != "source_id"}
    result = render(items=[item(), other, unbound])
    assert result["requests"] == [{"path": "/api/requirements?source_id=alphaxiv"}]
    assert "A saved direction" in result["list"]["text"]
    assert "Only B" not in result["list"]["text"] and "Unbound" not in result["list"]["text"]


def test_switching_sources_and_remounting_keeps_each_sources_own_draft():
    result = render(action="draft_switch")
    assert result["fields"]["requirement-content"]["value"] == "Draft A"
    assert result["b_fields"]["requirement-content"]["value"] == "Draft B"
    assert [request["path"] for request in result["requests"]] == ["/api/requirements?source_id=alphaxiv", "/api/requirements?source_id=x-self"]
    assert writes(result) == []


@pytest.mark.parametrize("action", ["late_source", "late_editor"])
def test_late_source_a_response_cannot_change_source_b_draft(action):
    result = render(action=action, items=[item()])
    assert result["b_fields"]["requirement-content"]["value"].startswith("Draft B before A")
    assert writes(result) == []
    if action == "late_source": assert "A saved direction" not in result["b_root"]["text"]


def test_planned_source_can_save_requirements_without_claiming_connection_or_execution():
    result = render(action="create", source_b=True, title="Future scope", content="My own-account scope")
    assert writes(result)[0]["body"]["source_id"] == "x-self"
    assert "不表示来源已连接" in result["root"]["text"]
    assert not any("/api/alphaxiv" in request["path"] for request in result["requests"])


def test_requirements_have_no_independent_navigation_or_page():
    from html.parser import HTMLParser
    class Navigation(HTMLParser):
        pages = []
        def handle_starttag(self, tag, attrs):
            value = dict(attrs).get("data-page")
            if value: self.pages.append(value)
    index = SCRIPT.with_name("index.html").read_text()
    parser = Navigation(); parser.feed(index)
    assert "requirements" not in parser.pages
    assert 'id="requirements-view"' not in index


def test_reloading_a_conflicting_id_cannot_move_another_sources_requirement():
    other = {**item(), "requirement_id": "req-other", "source_id": "x-self"}
    result = render(action="reload", items=[other], conflict=True, requirement_id="req-other", title="A draft", content="Keep A draft")
    assert "没有归属当前推荐源" in result["notice"]
    assert result["fields"]["requirement-content"]["value"] == "Keep A draft"
    assert writes(result)[0]["body"]["source_id"] == "alphaxiv"
