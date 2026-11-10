"""Offline source-plugin configuration journeys; no source or account execution."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src/scholar_workflow/research/recommendations/static"
NODE = shutil.which("node")
RUNNER = r"""
const fs=require("node:fs"),vm=require("node:vm");
const input=JSON.parse(fs.readFileSync(0,"utf8"));
const ids=new Map(),events={},reads=[],posts=[];let focused=null,conflicted=false;
class Element {
 constructor(tag){this.tagName=tag;this.children=[];this.dataset={};this.attributes={};this.listeners={};this._text="";this.value="";this.hidden=false;this.disabled=false;this.files=[];this.className="";
  this.classList={toggle:(name,on)=>{const values=new Set(this.className.split(" ").filter(Boolean));on?values.add(name):values.delete(name);this.className=[...values].join(" ");}};}
 get textContent(){return this._text+this.children.map(child=>child.textContent).join("");}
 set textContent(value){this._text=String(value);this.children=[];}
 append(...children){this.children.push(...children);} replaceChildren(...children){this._text="";this.children=[];this.append(...children);}
 setAttribute(key,value){this.attributes[key]=value;}removeAttribute(key){delete this.attributes[key];}
 addEventListener(key,fn){(this.listeners[key]||=[]).push(fn);}focus(){focused=this.id;}
 async fire(key){if(this.disabled)throw Error("disabled control "+this.id);for(const fn of this.listeners[key]||[])await fn({target:this,preventDefault(){}});}
 click(){return this.fire("click");}remove(){}select(){}querySelector(){return null;}
}
const get=id=>{if(!ids.has(id)){let e=new Element("div");e.id=id;ids.set(id,e);}return ids.get(id);};
for(const id of ["source-plugin-editor","source-plugin-output","source-plugin-latest","source-plugin-notice"])get(id).hidden=true;
const pages=["recommendations","sources","ingestion","settings","context"].map(page=>{let e=new Element("button");e.dataset.page=page;return e;});
let custom=structuredClone(input.plugin.source);
if(input.action==="disabled_complete")custom.enabled=false;
let builtin={...structuredClone(custom),source_id:"builtin-feed",name:"Packaged Feed",origin:"builtin",enabled:true,connection_status:"not_checked"};
let revision=3;
const catalog=()=>({revision,items:[builtin,{...custom,origin:"registered",connection_status:"not_checked"}]});
const api=async(path,body)=>{
 if(body)posts.push({path,body:structuredClone(body)});else reads.push(path);
 if(path==="/api/sources")return catalog();
 if(path.startsWith("/api/sources/export?")){let id=new URLSearchParams(path.split("?")[1]).get("source_id");return {schema_version:1,source:structuredClone(id===builtin.source_id?input.plugin.source:custom)};}
 if(path.startsWith("/api/sources/guide?"))return{source:custom,discovery:{method:"host_native",require_current_tool_schema:true},requirements:{items:[]}};
 if(path==="/api/sources/enabled"){custom.enabled=body.enabled;revision++;return{source:custom,revision,changed:true};}
 if(path==="/api/sources/import"){
  if(input.action.startsWith("conflict")&&!conflicted){conflicted=true;custom.purpose="New server purpose";revision=4;let e=new Error("CAS conflict");e.code=5;throw e;}
  custom=structuredClone(body.plugin.source);revision++;return{source:custom,revision,changed:true};
 }
 throw Error("Unexpected configuration request "+path);
};
const bridge={api,ready:Promise.resolve(),element:(tag,cls,text)=>{let e=new Element(tag);e.className=cls||"";if(text)e.textContent=text;return e;},externalLink:(text,url)=>{let e=new Element("a");e.textContent=text;e.href=url;return e;},closeDetail(){}};
const context={URL,URLSearchParams,Blob,JSON,Error,Promise,Set,Map,Date,Array,Number,TextEncoder,console,
 window:{ScholarRecommendations:bridge,history:{state:null,replaceState(){},pushState(){}},scrollY:0,scrollTo(){},confirm:()=>true,addEventListener(key,fn){(events[key]||=[]).push(fn);}},
 document:{getElementById:get,createElement:tag=>new Element(tag),querySelectorAll:()=>pages,addEventListener(){},body:new Element("body")},
 navigator:{clipboard:{writeText:async()=>{}}},sessionStorage:{getItem:()=>null,setItem(){},removeItem(){}},setTimeout,clearTimeout};
function all(node){return[node,...node.children.flatMap(all)];}
const find=(cls)=>all(get("sources-list")).find(e=>e.className.split(" ").includes(cls));
const settle=async()=>{for(let n=0;n<5;n++)await new Promise(setImmediate);};
(async()=>{
 vm.runInNewContext(fs.readFileSync(process.argv[1],"utf8"),context);await pages[1].fire("click");await settle();
 if(input.action==="toggle"){await find("source-enabled").fire("click");await settle();}
 if(input.action==="guide"){await find("source-guide").fire("click");await settle();}
 if(input.action==="import_preview"){
  get("source-plugin-file").files=[{name:"custom.json",size:1500,text:async()=>JSON.stringify(input.plugin)}];await get("source-plugin-file").fire("change");await settle();
 }
 if(["create","invalid_json"].includes(input.action)){await get("sources-new").fire("click");await settle();}
 if(["edit","cancel","conflict","conflict_retry"].includes(input.action)){await find("source-edit").fire("click");await settle();}
 if(["create","edit","cancel","conflict","conflict_retry","invalid_json"].includes(input.action)){
  let edited=structuredClone(input.plugin);edited.source.purpose="Human edited research scope";
  get("source-plugin-json").value=input.action==="invalid_json"?"{invalid":JSON.stringify(edited);await get("source-plugin-json").fire("input");
  if(input.action==="cancel")await get("source-plugin-cancel").fire("click");else await get("source-plugin-save").fire("click");await settle();
  if(input.action==="conflict_retry"){await get("source-plugin-adopt").fire("click");await get("source-plugin-save").fire("click");await settle();}
 }
 process.stdout.write(JSON.stringify({reads,posts,catalog:catalog(),editor_hidden:get("source-plugin-editor").hidden,draft:get("source-plugin-json").value,
  notice:get("source-plugin-notice").textContent,latest_hidden:get("source-plugin-latest").hidden,latest:get("source-plugin-latest-content").textContent,
  output_hidden:get("source-plugin-output").hidden,output:get("source-plugin-output-content").value,sources_text:get("sources-list").textContent,
  buttons:all(get("sources-list")).filter(e=>e.tagName==="button").map(e=>({text:e.textContent,cls:e.className})),focused}));
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1;});
"""


def plugin():
    return {"schema_version": 1, "source": {
        "source_id": "synthetic-lab", "name": "Synthetic Lab", "purpose": "Research updates",
        "status": "available", "enabled": True, "scope": "selected_channel", "plugin_version": "1.0.0",
        "interfaces": [{"kind": "mcp", "url": "https://example.org/mcp"}],
        "capabilities": ["research discovery"], "documentation": ["https://example.org/docs"],
        "agent": {"connection_name": "synthetic-lab", "instructions": "Use the native host connection.",
                  "operations": [{"operation_id": "discover", "description": "Read selected releases", "effect": "read",
                                  "inputs": "Selected topic", "outputs": "Candidate metadata"}]}}}


def journey(action):
    if not NODE:
        pytest.skip("Node is needed for the offline configuration UI harness")
    result = subprocess.run([NODE, "-e", RUNNER, str(STATIC / "workspace.js")],
                            input=json.dumps({"action": action, "plugin": plugin()}), text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_source_editor_import_is_preview_only():
    result = journey("import_preview")
    assert not result["editor_hidden"] and not result["posts"]
    assert json.loads(result["draft"]) == plugin()


@pytest.mark.parametrize("action", ["create", "edit"])
def test_source_editor_saves_only_explicit_package_and_catalog_revision(action):
    result = journey(action)
    assert result["posts"] == [{"path": "/api/sources/import", "body": {
        "expected_revision": 3, "plugin": {**plugin(), "source": {**plugin()["source"], "purpose": "Human edited research scope"}}}}]
    assert result["editor_hidden"]
    if action == "edit":
        assert "/api/sources/export?source_id=synthetic-lab" in result["reads"]


def test_source_editor_conflict_preserves_draft_and_shows_server_copy():
    result = journey("conflict")
    assert not result["editor_hidden"] and not result["latest_hidden"]
    assert "Human edited" in result["draft"] and "New server purpose" in result["latest"]
    assert "草稿" in result["notice"]


def test_source_editor_conflict_adoption_requires_an_explicit_action():
    result = journey("conflict_retry")
    assert [row["body"]["expected_revision"] for row in result["posts"]] == [3, 4]
    assert result["catalog"]["items"][1]["purpose"] == "Human edited research scope"


def test_source_editor_cancel_and_invalid_json_do_not_write():
    canceled = journey("cancel")
    assert canceled["editor_hidden"] and not canceled["posts"]
    invalid = journey("invalid_json")
    assert not invalid["editor_hidden"] and not invalid["posts"]
    assert "JSON" in invalid["notice"]


def test_source_plugin_toggle_is_data_only_and_builtin_definition_has_no_editor():
    result = journey("toggle")
    assert result["posts"] == [{"path": "/api/sources/enabled", "body": {
        "source_id": "builtin-feed", "enabled": False, "expected_revision": 3}}]
    assert sum("source-edit" in row["cls"] for row in result["buttons"]) == 1


def test_source_agent_guide_is_read_only_and_keeps_native_discovery_boundary():
    result = journey("guide")
    assert not result["posts"] and not result["output_hidden"]
    assert json.loads(result["output"])["discovery"]["require_current_tool_schema"]


def test_disabled_complete_package_keeps_its_definition_complete():
    result = journey("disabled_complete")
    assert not result["catalog"]["items"][1]["enabled"]
    assert result["sources_text"].count("使用说明完整") == 2
    assert "使用说明待补全" not in result["sources_text"]
    assert any(row["text"] == "启用" for row in result["buttons"])
