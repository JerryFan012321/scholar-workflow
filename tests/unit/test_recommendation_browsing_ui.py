"""Offline user journeys for a compact feed, full details and read-only sources.

The canceled alphaXiv console is intentionally absent. All responses below are
synthetic; no account, provider or agent is contacted or launched.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "src/scholar_workflow/research/recommendations/static"
NODE = shutil.which("node")
RUNNER = r"""
const fs=require("node:fs"),vm=require("node:vm");
const input=JSON.parse(fs.readFileSync(0,"utf8"));
let activeNode=null;
const windowEvents={},documentEvents={};
class Element{
 constructor(tag){this.tagName=tag.toLowerCase();this.className="";this.children=[];this.attributes={};this.dataset={};
  this.listeners={};this._text="";this.disabled=false;this.checked=false;this.hidden=false;this.value="";this.scrollTop=0;
  this.classList={toggle:(name,on)=>{const values=new Set(this.className.split(" ").filter(Boolean));
   on?values.add(name):values.delete(name);this.className=[...values].join(" ");}};}
 get textContent(){return this._text+this.children.map(node=>node.textContent).join("");}
 set textContent(text){this._text=String(text);this.children=[];}
 get childElementCount(){return this.children.length;}get options(){return this.children;}
 append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}replaceChildren(...nodes){this._text="";this.children=[];this.append(...nodes);}
 setAttribute(name,value){this.attributes[name]=String(value);}removeAttribute(name){delete this.attributes[name];}
 getAttribute(name){return this.attributes[name]??null;}
 addEventListener(name,callback){(this.listeners[name]||=[]).push(callback);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
 querySelectorAll(selector){return all(this,node=>selector.split(",").some(part=>matches(node,part.trim()))).filter(node=>node!==this);}
 closest(selector){let node=this;while(node){if(selector.split(",").some(part=>matches(node,part.trim())))return node;node=node.parentElement;}return null;}
 contains(node){return all(this,item=>item===node).length>0;}getClientRects(){return this.hidden?[]:[{}];}
 scrollIntoView(){}scrollTo(options){this.scrollTop=options?.top||0;}
 async fire(name,extra={}){if(this.disabled)throw Error("disabled control");
  await Promise.all((this.listeners[name]||[]).map(fn=>fn({target:this,preventDefault(){},stopPropagation(){},...extra})));}focus(){activeNode=this;}
}
function matches(node,selector){if(selector.startsWith("."))return node.className.split(" ").includes(selector.slice(1));if(selector==="[hidden]")return node.hidden;return node.tagName===selector;}
const ids=new Map();const get=id=>{if(!ids.has(id)){const item=new Element("div");item.id=id;ids.set(id,item);}return ids.get(id);};
for(const id of ["detail-overlay","ingestion-overlay","sources-view","ingestion-view","settings-view","context-view"])get(id).hidden=true;
const historyScope=new Element("div");historyScope.className="scope-note";get("ingestion-view").append(historyScope);
const pages=["recommendations","sources","ingestion","settings","context"].map(page=>{const e=new Element("button");e.dataset.page=page;return e;});
const tabs=["","unread","saved","selected","ignored"].map(decision=>{const e=new Element("button");e.dataset.decision=decision;return e;});
const storage=new Map(Object.entries(input.storage||{})),posts=[],reads=[],sessions=[];let current=input.candidate,releaseHeld=null,holdUsed=false;
let candidates=input.candidates||[current];
let contextRecord=input.context||{context:{content:"",revision:0},ranking:{status:"empty",revision:0},candidate_count:1};
const context={URL,URLSearchParams,Date,Math,JSON,Error,SyntaxError,Set,Map,TextEncoder,Uint8Array,setTimeout,clearTimeout,
 window:{confirm:()=>true,location:{hash:input.fragment||"",pathname:"/",search:""},scrollY:0,scrollTo(options){this.scrollY=typeof options==="object"?options.top:0;},addEventListener(name,fn){(windowEvents[name]||=[]).push(fn);},
  history:{state:null,stack:[null],index:0,replaceState(value){this.state=value;this.stack[this.index]=value;},pushState(value){this.state=value;this.stack=this.stack.slice(0,++this.index);this.stack.push(value);},back(){if(this.index>0){this.state=this.stack[--this.index];for(const fn of windowEvents.popstate||[])fn({state:this.state});}}},crypto:{randomUUID:()=>"safe-fixture-id"}},
 document:{getElementById:get,createElement:tag=>new Element(tag),body:new Element("body"),
  get activeElement(){return activeNode;},querySelectorAll:selector=>selector==="[data-page]"?pages:tabs,addEventListener(name,fn){(documentEvents[name]||=[]).push(fn);}},
 sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 fetch:async(path,options={})=>{
  if(path==="/api/session"){sessions.push(options);return {ok:!input.session_failure,status:input.session_failure?403:200,json:async()=>({token:input.session_failure?null:"a".repeat(32)})};}
  const payload=options.method==="POST"?JSON.parse(options.body):null;
  if(payload)posts.push({path,body:payload});else reads.push(path);
  if(!holdUsed&&((input.action==="reopen_ingestion_plan"&&path==="/api/ingestion/plan")||
    (input.action==="reopen_ingestion_execute"&&path==="/api/ingestion/execute"))){holdUsed=true;await new Promise(resolve=>{releaseHeld=resolve;});}
  if(input.action==="review_conflict"&&path==="/api/reviews")return{ok:false,status:409,json:async()=>({exit_code:5})};
  if(input.action==="revoke_conflict"&&path==="/api/reviews/revoke")return{ok:false,status:409,json:async()=>({exit_code:5})};
  if(input.action==="revoke_error"&&path==="/api/reviews/revoke")return{ok:false,status:503,json:async()=>({exit_code:3})};
  if(input.action==="context_conflict"&&path==="/api/ranking/context"&&payload)return{ok:false,status:409,json:async()=>({exit_code:5})};
  if(input.action==="evaluation_conflict"&&path==="/api/evaluations")return{ok:false,status:409,json:async()=>({exit_code:5})};
  if(input.action==="evaluation_error"&&path==="/api/evaluations")return{ok:false,status:503,json:async()=>({exit_code:3})};
  if(input.action==="tags_conflict"&&path==="/api/tags")return{ok:false,status:409,json:async()=>({exit_code:5})};
  let value;
  if(path==="/health")value={profile:input.profile||"test",pool_id:input.pool_id||"pool-"+"b".repeat(32)};
  else if(path.startsWith("/api/candidates")){const params=new URLSearchParams(path.split("?")[1]||"");let rows=candidates.map(row=>row.candidate_id===current.candidate_id?current:row);if(params.get("decision"))rows=rows.filter(row=>row.decision===params.get("decision"));value={items:rows.slice(Number(params.get("offset")||0),Number(params.get("offset")||0)+Number(params.get("limit")||40)),total:rows.length,facets:{tags:[],producers:[],kinds:["paper"]}};}
  else if(path==="/api/reviews"){current={...current,revision:current.revision+1,abstract_reviewed:true};value=current;}
  else if(path==="/api/reviews/revoke"){current={...current,revision:current.revision+1,abstract_reviewed:false,decision:current.decision==="selected"?"unread":current.decision};value=current;}
  else if(path==="/api/decisions"){
   if(input.decision_failure)return{ok:false,status:409,json:async()=>({exit_code:5})};
   current={...current,revision:current.revision+1,decision:payload.decision,
    disposition:payload.reason?{reason:payload.reason,scope:payload.scope||(payload.reason==="not_relevant"?"current_research":null)}:null};value=current;
  }
  else if(path==="/api/tags"||path==="/api/tags/reset"){current={...current,revision:current.revision+1,tags:payload.tags||["original"]};value=current;}
  else if(path==="/api/metrics")value=current;
  else if(path==="/api/ranking/context"){
   if(payload)contextRecord={...contextRecord,context:{content:payload.content,revision:contextRecord.context.revision+1,updated_by:{name:"推荐页"},updated_at:"2026-11-10T00:00:00Z"}};
   value=contextRecord;
  }
  else if(path==="/api/evaluations"){current={...current,evaluation:{score:payload.score,comment:payload.comment,
    revision:payload.expected_revision+1,updated_at:"2026-11-10T00:00:00Z",matches_current_content:true}};value=current;}
  else if(path==="/api/sources")value={items:[{source_id:"alphaxiv",name:"alphaXiv",purpose:"Popular research discovery and optional native researcher/library management.",status:"available",enabled:true,scope:"authorized_account",interfaces:[{kind:"mcp",url:"https://api.alphaxiv.org/mcp/v1"}],capabilities:["popular research feed","personalized research feed"],documentation:["https://www.alphaxiv.org/docs/mcp"],auth:{method:"host_oauth",reference:"host:alphaxiv",instructions:"The host owns OAuth."},execution:{kind:"native_mcp",host_connection_name:"alphaxiv"},origin:"builtin",connection_status:"not_checked"},{source_id:"x-self",name:"X — own-account curated posts",purpose:"Future own account collection.",status:"planned",enabled:false,scope:"self_account_only",interfaces:[{kind:"api",url:"https://api.x.com/2/"}],capabilities:["own reposts"],documentation:["https://docs.x.com/x-api/users/get-posts"],auth:{method:"not_configured",instructions:"Future own account only."},execution:{kind:"planned"},connection_status:"not_implemented"}]};
  else if(path.startsWith("/api/requirements?"))value={items:[]};
  else if(path==="/api/ingestion/targets")value={available:true,targets:[{key:"ABCDEFGH",name:"World Models"},{key:"IJKLMNOP",name:"Other"}]};
  else if(path==="/api/ingestion/plan")value={plan_id:"plan-synthetic",title:current.resource.title,collection:{key:"ABCDEFGH",name:"World Models"},item_type:"preprint",existing:input.existing||false,warnings:["PDF 尚未保存。"]};
  else if(path==="/api/ingestion/execute"){value={status:"completed",item_key:"1234ABCD",collection_key:"ABCDEFGH",title:current.resource.title};current={...current,ingestion:value};}
  else if(path==="/api/ingestion/history")value={items:input.history||[{status:"completed",item_key:"1234ABCD",title:current.resource.title,collection:{name:"World Models"},completed_at:"2026-11-09T00:00:00Z"}]};
  else if(path==="/api/intake/history")value={items:[],configuration:{revision:0,enabled:false,collection_key:null,collection_name:null}};
  else if(path==="/api/intake/configuration")value={revision:1,enabled:payload.enabled,collection_key:payload.collection_key,collection_name:"World Models"};
  else throw Error("Unexpected request "+path);
  return{ok:true,status:200,json:async()=>value};
 }};
function find(node,predicate){if(predicate(node))return node;for(const child of node.children){const hit=find(child,predicate);if(hit)return hit;}}
function all(node,predicate){return [...(predicate(node)?[node]:[]),...node.children.flatMap(child=>all(child,predicate))];}
function snap(node){return{tag:node.tagName,class:node.className,text:node.textContent,value:node.value,hidden:node.hidden,disabled:node.disabled,
 open:node.open,dataset:node.dataset,scrollTop:node.scrollTop,
 href:node.href||null,title:node.title||null,dateTime:node.dateTime||null,attributes:node.attributes,children:node.children.map(snap)};}
const settle=async()=>{for(let n=0;n<7;n++)await new Promise(setImmediate);};
const byClass=(id,name)=>find(get(id),node=>node.className.split(" ").includes(name));
const openDetails=async()=>{await byClass("feed","entry-details").fire("click");await settle();};
(async()=>{
 vm.runInNewContext(fs.readFileSync(process.argv[1],"utf8"),context);
 vm.runInNewContext(fs.readFileSync(process.argv[2],"utf8"),context);
 vm.runInNewContext(fs.readFileSync(process.argv[3],"utf8"),context);await settle();
 // Existing reading journeys explicitly browse All; fresh-home journeys exercise the real default.
 if(!input.fresh_home&&!input.session_failure){await tabs.find(tab=>tab.dataset.decision==="").fire("click");await settle();}
 const initial=snap(get("feed"));let settingsJourney=null;
 if(!["sources","history","initial","source_requirements","settings_roundtrip"].includes(input.action)&&!input.action.startsWith("context_")&&!input.action.startsWith("quick_")&&!input.action.startsWith("filter_")){await openDetails();}
 if(input.action.startsWith("tags_")){
  const picker=byClass("detail-content","tag-picker");picker.open=true;await picker.fire("toggle");
  const search=byClass("detail-content","tag-search");search.value=input.action==="tags_existing"?"jep":"场景编排";await search.fire("input");
  if(input.action==="tags_reset")await byClass("detail-content","tag-reset").fire("click");
  else if(input.action==="tags_existing")await byClass("detail-content","tag-option").fire("click");
  else if(input.action==="tags_closed_undo"){picker.open=false;await byClass("detail-content","tag-remove").fire("click");}
  else if(input.action==="tags_remove")await byClass("detail-content","tag-remove").fire("click");
  else if(input.action==="tags_escape")await search.fire("keydown",{key:"Escape"});
  else if(input.action!=="tags_search")await search.fire("keydown",{key:"Enter"});
  await settle();
  if(["tags_undo","tags_closed_undo"].includes(input.action)){await byClass("detail-content","tag-undo").fire("click");await settle();}
 }

 if(input.action==="reopen_detail"){await get("detail-close").fire("click");if(get("detail-content").childElementCount)throw Error("detail body not cleared");await openDetails();}
 if(input.action==="sources_then_ingest"){await pages[1].fire("click");await settle();await pages[0].fire("click");await settle();await openDetails();}
 if(["review","review_conflict","review_then_select"].includes(input.action)){
  const checkbox=byClass("detail-content","review").children.find(node=>node.tagName==="input");
  await checkbox.fire("change");await settle();
 }
 if(input.action==="review_then_select"){
  const checkbox=byClass("detail-content","select-input");checkbox.checked=true;await checkbox.fire("change");await settle();
 }
 if(["revoke","revoke_conflict","revoke_error"].includes(input.action)){
  await byClass("detail-content","review-revoke").fire("click");await settle();
 }
 if(input.action.startsWith("evaluation_")){
  if(input.action==="evaluation_clear"){
   await byClass("detail-content","evaluation-clear").fire("click");await settle();
  }else{
   const section=byClass("detail-content","evaluation");section.open=true;
   if(input.action!=="evaluation_comment_only"){
    const score=find(section,node=>node.className==="evaluation-score"&&node.textContent==="4 分");await score.fire("click");
   }
   const comment=byClass("detail-content","evaluation-comment");comment.value=input.comment||"方法有参考价值。";await comment.fire("input");
   if(input.action==="evaluation_draft_reopen"){
    await get("detail-close").fire("click");await openDetails();
   }else{await byClass("detail-content","evaluation-save").fire("click");await settle();}
  }
 }
 if(["ingest","plan","change_target","reopen_ingestion_plan","reopen_ingestion_execute","sources_then_ingest"].includes(input.action)){
  const open=byClass("detail-content","ingestion-open");await open.fire("click");await settle();
  get("ingestion-collection").value="ABCDEFGH";
  if(input.action==="reopen_ingestion_plan"){
   const pending=get("ingestion-preview").fire("click");await settle();await get("ingestion-close").fire("click");await open.fire("click");await settle();releaseHeld();await pending;await settle();
  }else{await get("ingestion-preview").fire("click");await settle();}
  if(input.action==="change_target"){get("ingestion-collection").value="IJKLMNOP";await get("ingestion-collection").fire("change");}
  if(input.action==="reopen_ingestion_execute"){
   const pending=byClass("ingestion-plan","ingestion-execute").fire("click");await settle();await get("ingestion-close").fire("click");await open.fire("click");await settle();releaseHeld();await pending;await settle();
  }
  if(["ingest","sources_then_ingest"].includes(input.action)){await byClass("ingestion-plan","ingestion-execute").fire("click");await settle();}
 }
 if(input.action==="sources"){await pages[1].fire("click");await settle();}
 if(input.action==="history"){await pages[2].fire("click");await settle();}
 if(input.action==="intake_settings"){
  await pages[2].fire("click");await settle();
  get("intake-target-collection").value="ABCDEFGH";
  await get("intake-target-save").fire("click");await settle();
 }
 if(input.action==="reject_quality"){
  const panel=byClass("detail-content","rejection-picker");
  if(find(panel,node=>node.tagName==="button"&&node.textContent==="质量不符合要求"))throw new Error("Quality belongs outside ignore");
  await find(get("detail-content"),node=>node.tagName==="button"&&node.textContent==="质量不符合要求").fire("click");await settle();
 }
 if(input.action==="reject_scope"){
  const panel=byClass("detail-content","rejection-picker");
  if(byClass("detail-content","rejection-scope"))throw new Error("Unexpected relevance scope input");
  await find(panel,node=>node.tagName==="button"&&node.textContent==="不是当前想关注的方向").fire("click");await settle();
 }
 if(input.action==="reject_other"){
  const panel=byClass("detail-content","rejection-picker");
  await find(panel,node=>node.tagName==="button"&&node.textContent==="其他").fire("click");await settle();
 }
 if(input.action==="source_requirements"){
  await pages[1].fire("click");await settle();
  const fold=byClass("sources-list","source-requirements");fold.open=true;await fold.fire("toggle");await settle();
  fold.open=false;await fold.fire("toggle");fold.open=true;await fold.fire("toggle");await settle();
 }
 if(input.action==="settings_roundtrip"){
  get("query").value="draft search kept";
  get("sort").value="oldest";await get("sort").fire("change");await settle();
  const readCount=reads.length;
  await pages[3].fire("click");await settle();
  const sourcesVisible=!get("settings-view").hidden&&!get("sources-view").hidden&&get("recommendations-view").hidden;
  await pages[2].fire("click");await settle();
  const historyVisible=!get("settings-view").hidden&&!get("ingestion-view").hidden&&get("sources-view").hidden;
  await pages[0].fire("click");await settle();
  settingsJourney={sourcesVisible,historyVisible,query:get("query").value,sort:get("sort").value,reads:reads.slice(readCount)};
 }
 if(input.action.startsWith("context_")){
  await pages[3].fire("click");await settle();await pages[4].fire("click");await settle();
  if(input.action!=="context_initial"){get("ranking-context-content").value="本轮关注世界模型。保留我的判断。";await get("ranking-context-content").fire("input");}
  if(input.action==="context_roundtrip"){
   await pages[0].fire("click");await pages[3].fire("click");await settle();
  }
  if(["context_save","context_conflict"].includes(input.action)){await get("ranking-context-save").fire("click");await settle();}
 }
 if(input.action==="quick_save"||input.action==="quick_undo"){
  await byClass("feed","entry-save").fire("click");await settle();
  if(input.action==="quick_undo"){await byClass("notice","notice-undo").fire("click");await settle();}
 }
 if(input.action.startsWith("quick_feedback")){
  if(input.action==="quick_feedback_last_page"){await get("next").fire("click");await settle();}
  const menu=byClass("feed","entry-more");menu.open=true;await menu.fire("toggle");
  if(input.action==="quick_feedback_escape"){await menu.fire("keydown",{key:"Escape"});}
  else if(input.action==="quick_feedback_outside"){for(const fn of documentEvents.click||[])fn({target:get("result-count")});}
  else{
   const key={quality:"entry-quality",not_relevant:"entry-unrelated",other:"entry-other",restore:"entry-restore"}[input.reason||"quality"];
   await byClass("feed",key).fire("click");await settle();
   if(input.action==="quick_feedback_undo"){await byClass("notice","notice-undo").fire("click");await settle();}
  }
 }
 if(input.action==="quick_all"){await get("empty-all").fire("click");await settle();}
 if(input.action==="reader_next"||input.action==="reader_next_previous"){
  get("detail-panel").scrollTop=500;await get("detail-next").fire("click");await settle();
  if(input.action==="reader_next_previous"){await get("detail-previous").fire("click");await settle();}
 }
 if(input.action==="reader_page_boundary"){
  for(let n=0;n<20;n++){await get("detail-next").fire("click");await settle();}
 }
 if(input.action==="reader_update_scroll"){
  get("detail-panel").scrollTop=420;await byClass("detail-content","review-revoke").fire("click");await settle();
 }
 if(input.action==="reader_back"){
  context.window.history.back();await settle();
 }
 if(input.action==="reader_keyboard_in_text"){
  const editor=byClass("detail-content","evaluation-comment");editor.tagName="textarea";
  for(const fn of documentEvents.keydown||[])fn({key:"j",target:editor,preventDefault(){}});await settle();
 }
 if(input.action==="reader_keyboard_next"){
  for(const fn of documentEvents.keydown||[])fn({key:"j",target:get("detail-next"),preventDefault(){}});await settle();
 }
 if(input.action==="filter_remove"){
  get("kind").value="paper";await get("kind").fire("change");await settle();
  await byClass("active-filters","filter-chip").fire("click");await settle();
 }
 process.stdout.write(JSON.stringify({posts,reads,sessions,initial,notice:snap(get("notice")),tabs:tabs.map(snap),
  page_number:get("page-number").textContent,empty_title:get("empty-title").textContent,empty_all_hidden:get("empty-all").hidden,feed:snap(get("feed")),detail:snap(get("detail-content")),
  reader_position:get("detail-position").textContent,reader_scroll:get("detail-panel").scrollTop,reader_next_disabled:get("detail-next").disabled,reader_previous_disabled:get("detail-previous").disabled,filters:snap(get("active-filters")),filter_summary:get("filter-summary").textContent,storage:Object.fromEntries(storage),
  detail_hidden:get("detail-overlay").hidden,detail_notice:get("detail-notice").textContent,sources:snap(get("sources-list")),
  history:snap(get("ingestion-history")),plan:snap(get("ingestion-plan")),collection:snap(get("ingestion-collection")),
  preview:snap(get("ingestion-preview")),modal:snap(get("ingestion-overlay")),
  dialog_title:get("ingestion-dialog-title").textContent,history_scope:snap(historyScope),
  settingsJourney,settings_hidden:get("settings-view").hidden,
  context:{content:get("ranking-context-content").value,meta:get("ranking-context-meta").textContent,state:get("ranking-context-state").textContent,
   notice:get("ranking-context-notice").textContent,save_disabled:get("ranking-context-save").disabled,hidden:get("context-view").hidden},
  views:Object.fromEntries(["recommendations","sources","ingestion"].map(page=>[page,get(page+"-view").hidden]))}));
})().catch(error=>{process.stderr.write(String(error.stack));process.exitCode=1;});
"""


def candidate(**extra):
    return {"candidate_id": "candidate-" + "a" * 64, "revision": 3,
            "resource": {"kind": "paper", "title": "Synthetic paper", "url": "https://arxiv.org/abs/2601.12345",
                         "authors": ["A. Researcher", "B. Researcher"], "abstract_original": "Complete original abstract with source context.",
                         "abstract_zh": "这是完整摘要中的具体内容。" * 30 + "这是完整摘要的最后一句。",
                         "project_url": "https://example.org/project", "links": [
                             {"label": "官方 Blog", "kind": "blog", "url": "https://example.org/blog"},
                             {"label": "已核验版本", "url": "https://arxiv.org/abs/2601.12345v2"},
                             {"label": "原文许可", "url": "https://creativecommons.org/licenses/by/4.0/"}]},
            "decision": "selected", "abstract_reviewed": True, "review_required": True, "review_available": True,
            "metrics": [], "metric_targets": [], "producers": [{"name": "专项推荐 agent", "producer_id": "field-agent"}],
            "recommendations": [{"producer": {"name": "专项推荐 agent"}, "received_at": "2026-11-09T00:00:00Z", "tags": ["world-models"], "channels": [{"name": "alphaXiv", "url": "https://www.alphaxiv.org/"}]}],
            "tags": ["world-models", "jepa"], **extra}


def render(**scenario):
    if not NODE: pytest.skip("System Node is required for isolated browser scenarios.")
    result = subprocess.run([NODE, "-e", RUNNER, str(STATIC / "app.js"), str(STATIC / "workspace.js"), str(STATIC / "requirements.js")],
                            input=json.dumps({"candidate": candidate(), "action": "initial", **scenario}),
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_configured_intake_selection_needs_no_second_preview_action():
    result = render(action="review_then_select", candidate=candidate(decision="unread", abstract_reviewed=False,
                    intake_target={"collection_name": "待整理条目"}, intake_job=None))
    assert [post["path"] for post in result["posts"]] == ["/api/reviews", "/api/decisions"]
    assert not nodes(result["detail"], "ingestion-open")
    assert "选择后自动接收到 待整理条目" in result["detail"]["text"]


def test_unconfigured_new_intake_routes_to_settings_without_claiming_ingestion():
    result = render(action="details", candidate=candidate(intake_target=None, intake_job=None))
    assert "先在设置中指定待整理条目的接收分类" in result["detail"]["text"]
    assert not nodes(result["detail"], "ingestion-open")
    assert not result["posts"]


def test_receiving_target_is_configured_once_under_settings():
    result = render(action="intake_settings", candidate=candidate(intake_target=None))
    assert result["posts"] == [{"path": "/api/intake/configuration", "body": {
        "collection_key": "ABCDEFGH", "expected_revision": 0, "enabled": True}}]


@pytest.mark.parametrize("action,reason", [("reject_quality", "quality"), ("reject_scope", "not_relevant"), ("reject_other", "other")])
def test_rejection_interaction_preserves_quality_vs_direction_meaning(action, reason):
    result = render(action=action, candidate=candidate(intake_target=None))
    assert result["posts"][-1]["body"]["reason"] == reason
    assert result["posts"][-1]["body"]["decision"] == "ignored"
    if reason == "not_relevant":
        assert "scope" not in result["posts"][-1]["body"]


def nodes(tree, name):
    return ([tree] if name in tree["class"].split() else []) + [node for child in tree["children"] for node in nodes(child, name)]


def test_initial_feed_is_compact_and_does_not_render_full_detail_assets():
    result = render()
    assert nodes(result["feed"], "compact-card")
    assert "这是完整摘要的最后一句。" not in result["feed"]["text"]
    assert "热度待补齐" in result["feed"]["text"]
    assert "alphaXiv" in result["feed"]["text"]
    assert not nodes(result["feed"], "metrics")
    assert not nodes(result["feed"], "review")
    assert not nodes(result["feed"], "links")
    assert not nodes(result["feed"], "ingestion-open")
    assert result["detail_hidden"] and not result["detail"]["children"]
    assert result["posts"] == []
    assert all(path == "/health" or path.startswith("/api/candidates") for path in result["reads"])


def test_home_navigation_has_only_settings_gear_not_source_or_history_tabs():
    html = (STATIC / "index.html").read_text()
    header = html.split("<main>", 1)[0]
    assert 'aria-label="打开设置"' in header and 'data-page="settings"' in header
    assert 'data-page="sources"' not in header and 'data-page="ingestion"' not in header
    settings = html.split('<section id="settings-view"', 1)[1]
    assert 'data-page="sources"' in settings and 'data-page="ingestion"' in settings
    assert 'data-page="recommendations"' in settings
    assert render()["settings_hidden"]


def test_settings_context_is_blank_until_human_or_external_agent_fills_it():
    result = render(action="context_initial")
    assert result["context"]["content"] == "" and "第 0 版" in result["context"]["meta"]
    assert not result["context"]["hidden"] and result["context"]["save_disabled"]
    assert result["context"]["state"] == "尚无外部 agent 排序"
    assert not result["posts"]


def test_settings_context_saves_only_content_and_current_revision():
    result = render(action="context_save")
    assert result["posts"] == [{"path": "/api/ranking/context", "body": {
        "content": "本轮关注世界模型。保留我的判断。", "expected_revision": 0}}]
    assert "第 1 版" in result["context"]["meta"] and "上下文已保存" in result["context"]["notice"]


def test_settings_context_draft_survives_navigation_and_conflict():
    for action in ["context_roundtrip", "context_conflict"]:
        result = render(action=action)
        assert result["context"]["content"] == "本轮关注世界模型。保留我的判断。"
        assert result["reads"].count("/api/ranking/context") == (2 if action == "context_conflict" else 1)
        assert not result["context"]["save_disabled"]
        if action == "context_conflict":
            assert "当前草稿已保留" in result["context"]["notice"]


@pytest.mark.parametrize("status,label", [("empty", "尚无外部 agent 排序"), ("current", "排序已更新"), ("stale", "输入已变化，等待更新")])
def test_settings_context_reports_actual_external_ranking_state(status, label):
    result = render(action="context_initial", context={"context": {"content": "saved", "revision": 2}, "ranking": {"status": status}})
    assert result["context"]["state"] == label


def test_settings_gear_opens_sources_and_records_without_resetting_recommendations():
    result = render(action="settings_roundtrip")
    journey = result["settingsJourney"]
    assert journey["sourcesVisible"] and journey["historyVisible"]
    assert journey["query"] == "draft search kept" and journey["sort"] == "oldest"
    assert journey["reads"] == ["/api/sources", "/api/ingestion/history", "/api/intake/history", "/api/ingestion/targets"]
    assert result["settings_hidden"] and not result["views"]["recommendations"]
    assert result["initial"]["text"] == result["feed"]["text"]
    assert "alphaXiv" in result["sources"]["text"] and "书目" in result["history"]["text"]
    assert not result["posts"]


def test_detail_preserves_complete_translation_original_and_every_attachment():
    result = render(action="detail")
    assert not result["detail_hidden"]
    assert candidate()["resource"]["abstract_zh"] in result["detail"]["text"]
    assert candidate()["resource"]["abstract_original"] in result["detail"]["text"]
    links = nodes(result["detail"], "links")[0]["children"]
    assert {link["href"] for link in links} == {candidate()["resource"]["url"], candidate()["resource"]["project_url"], *[link["url"] for link in candidate()["resource"]["links"]]}
    assert nodes(result["detail"], "summary-label")[0]["text"] == "摘要"
    provenance = nodes(result["detail"], "provenance")[0]
    assert provenance["tag"] == "details" and not provenance.get("open", False)
    assert provenance["children"][0]["text"] == "出处"
    assert nodes(result["detail"], "review")
    assert nodes(result["detail"], "ingestion-open")
    assert "专项推荐 agent" in result["detail"]["text"]


def test_reading_content_and_links_precede_metadata_controls_in_both_views():
    result = render(action="detail")
    classes = [child["class"].split(" ")[0] for child in result["detail"]["children"][0]["children"]]
    assert classes.index("summary") < classes.index("links") < classes.index("metrics") < classes.index("evaluation")
    assert classes.index("summary") < classes.index("tag-manager")
    compact = [child["class"] for child in result["feed"]["children"][0]["children"]]
    assert compact.index("compact-introduction") < compact.index("compact-tags")


def test_detail_close_then_reopen_has_complete_current_content():
    result = render(action="reopen_detail")
    assert candidate()["resource"]["abstract_zh"] in result["detail"]["text"]
    assert len(nodes(result["detail"], "links")[0]["children"]) == 5


def test_review_and_selection_keep_exact_current_revisions_in_details():
    result = render(action="review_then_select", candidate=candidate(abstract_reviewed=False, decision="unread"))
    assert result["posts"] == [{"path": "/api/reviews", "body": {"candidate_id": candidate()["candidate_id"], "expected_revision": 3}},
                               {"path": "/api/decisions", "body": {"candidate_id": candidate()["candidate_id"], "expected_revision": 4, "decision": "selected"}}]
    assert not nodes(result["detail"], "ingestion-open")[0]["disabled"]


def test_review_conflict_stays_visible_inside_the_open_details():
    result = render(action="review_conflict", candidate=candidate(abstract_reviewed=False))
    assert "发生变化" in result["detail_notice"]
    assert len(result["posts"]) == 1


def test_evaluation_saves_own_revision_and_shows_only_compact_score_in_feed():
    result = render(action="evaluation_save", comment="方法可用，先检查成本。")
    assert result["posts"] == [{"path": "/api/evaluations", "body": {
        "candidate_id": candidate()["candidate_id"], "expected_revision": 0, "expected_candidate_revision": 3,
        "score": 4, "comment": "方法可用，先检查成本。"}}]
    assert "★★★★☆ 4/5" in result["feed"]["text"]
    assert "方法可用，先检查成本。" not in result["feed"]["text"]
    assert nodes(result["detail"], "evaluation-comment")[0]["value"] == "方法可用，先检查成本。"
    assert not nodes(result["detail"], "evaluation-save")[0]["disabled"]
    assert "评价已保存" in result["detail_notice"]


def test_evaluation_comment_is_optional_and_clear_is_explicit():
    result = render(action="evaluation_comment_only", comment="<script>synthetic text only</script>")
    assert result["posts"][0]["body"]["score"] is None
    assert nodes(result["feed"], "compact-evaluation")[0]["text"] == "我的评价 已评价"
    assert nodes(result["detail"], "evaluation-comment")[0]["value"] == "<script>synthetic text only</script>"
    result = render(action="evaluation_clear", candidate=candidate(evaluation={
        "score": 2, "comment": "旧评价", "revision": 8, "matches_current_content": True}))
    assert result["posts"][0]["body"] == {"candidate_id": candidate()["candidate_id"],
        "score": None, "comment": "", "expected_revision": 8, "expected_candidate_revision": 3}
    assert not nodes(result["feed"], "compact-evaluation")
    assert "评价已清除" in result["detail_notice"]


@pytest.mark.parametrize("action", ["evaluation_conflict", "evaluation_error", "evaluation_draft_reopen"])
def test_evaluation_keeps_draft_after_conflict_failure_or_detail_reopen(action):
    result = render(action=action, comment="尚未保存的详细意见")
    assert nodes(result["detail"], "evaluation-comment")[0]["value"] == "尚未保存的详细意见"
    if action == "evaluation_draft_reopen":
        assert not result["posts"]
    else:
        assert "草稿已保留" in nodes(result["detail"], "evaluation-feedback")[0]["text"]
        assert not nodes(result["detail"], "evaluation-save")[0]["disabled"]
        assert nodes(result["detail"], "evaluation-restore")[0]["hidden"] == (action != "evaluation_conflict")


def test_evaluation_is_available_without_review_and_changed_content_is_explicit():
    result = render(action="detail", candidate=candidate(abstract_reviewed=False, decision="unread", evaluation={
        "score": 3, "comment": "旧内容的意见", "revision": 2, "matches_current_content": False}))
    assert "评价后资料已更新" in result["detail"]["text"]
    assert not nodes(result["detail"], "evaluation-save")[0]["disabled"]


def test_reading_source_settings_never_calls_mcp_or_launches_an_agent():
    result = render(action="sources")
    assert result["views"] == {"recommendations": True, "sources": False, "ingestion": True}
    assert "alphaXiv" in result["sources"]["text"]
    assert "已启用" in result["sources"]["text"] and "计划接入" in result["sources"]["text"]
    assert "连接未检查" in result["sources"]["text"] and "连接尚未实现" in result["sources"]["text"]
    assert "https://api.alphaxiv.org/mcp/v1" in result["sources"]["text"]
    assert "由 agent 宿主授权" in result["sources"]["text"]
    assert "工具由 agent 宿主发现" in result["sources"]["text"]
    assert "alphaxiv" in result["sources"]["text"]
    assert result["posts"] == []
    assert "/api/sources" in result["reads"]
    assert not any("/api/alphaxiv" in path for path in result["reads"])
    assert not nodes(result["sources"], "tool-form")


def test_raw_metrics_remain_small_and_zero_is_not_lost():
    item = candidate(metrics=[{"platform": "github", "metric": "stars", "value": 0, "url": "https://github.com/example/model", "observed_at": "2026-11-09T00:00:00Z"}])
    result = render(candidate=item)
    assert "GitHub stars 0" in result["feed"]["text"]
    assert "热度待补齐" not in result["feed"]["text"]
    assert not nodes(result["feed"], "metrics")


def test_direct_ingestion_uses_preview_then_confirmation_from_details():
    result = render(action="ingest", profile="personal")
    assert result["posts"] == [{"path": "/api/ingestion/plan", "body": {"candidate_id": candidate()["candidate_id"], "expected_revision": 3, "collection_key": "ABCDEFGH"}},
                               {"path": "/api/ingestion/execute", "body": {"plan_id": "plan-synthetic", "confirmed": True}}]
    assert "书目已入库" in result["feed"]["text"]
    assert "Zotero 书目已入库" in result["detail"]["text"]
    assert "PDF 与 Vault 归档另行处理" in result["plan"]["text"]


def test_changed_target_hides_old_plan():
    result = render(action="change_target")
    assert result["plan"]["hidden"]
    assert not [post for post in result["posts"] if post["path"] == "/api/ingestion/execute"]


@pytest.mark.parametrize("phase", ["plan", "execute"])
def test_reopened_ingestion_restores_controls_after_old_request_finishes(phase):
    result = render(action="reopen_ingestion_" + phase)
    assert not result["collection"]["disabled"] and not result["preview"]["disabled"]
    assert not result["modal"]["hidden"] and result["plan"]["hidden"]


def test_unreviewed_or_unselected_detail_cannot_start_ingestion():
    for item in [candidate(abstract_reviewed=False), candidate(decision="unread")]:
        result = render(action="detail", candidate=item)
        assert nodes(result["detail"], "ingestion-open")[0]["disabled"]
        assert not result["posts"]


def test_previous_content_receipt_does_not_claim_current_content_is_ingested():
    result = render(action="detail", candidate=candidate(ingestion={"status": "completed", "matches_current_content": False}))
    assert "旧内容有入库记录" in result["feed"]["text"]
    assert "旧内容已有入库记录，当前内容已更新" in result["detail"]["text"]
    assert "Zotero 书目已入库" not in result["detail"]["text"]


@pytest.mark.parametrize("existing", [False, True])
def test_plan_explains_type_and_create_or_reuse(existing):
    result = render(action="plan", existing=existing, profile="personal")
    assert "书目类型：预印本" in result["plan"]["text"]
    assert ("本次将复用" if existing else "本次将创建") in result["plan"]["text"]


def test_history_keeps_scope_native_item_link_and_readable_time():
    result = render(action="history", profile="personal")
    assert "PDF 与 Vault 归档另行处理" in result["history"]["text"]
    assert "书目已入库" in result["history"]["text"]
    row = result["history"]["children"][0]
    assert row["tag"] == "details"
    assert row["children"][0]["tag"] == "summary"
    card = row["children"][1]["children"][0]
    assert any(child["href"] == "zotero://select/library/items/1234ABCD" for child in card["children"])
    time = card["children"][2]["children"][3]["children"][0]
    assert time["title"] == time["dateTime"] == "2026-11-09T00:00:00Z" and "北京时间" in time["text"]


def test_switching_pages_does_not_register_duplicate_ingestion_actions():
    result = render(action="sources_then_ingest")
    calls = [post["path"] for post in result["posts"]]
    assert calls == ["/api/ingestion/plan", "/api/ingestion/execute"]


def test_requirement_snapshot_is_complete_and_scoped_to_its_recommendation_details():
    item = candidate()
    item["recommendations"][0]["requirement"] = {"requirement_id": "req-world-models", "revision": 2,
        "title": "世界模型专项", "content": "只关注当前项目相关的资料。\n" + "进一步要求与原始条件。" * 30 + "快照末尾。", "enabled": True}
    result = render(action="detail", candidate=item)
    assert "当时的推荐要求" not in result["initial"]["text"]
    snapshots = nodes(result["detail"], "recommendation-requirement")
    assert len(snapshots) == 1
    assert "世界模型专项 · 第 2 版" in snapshots[0]["text"]
    assert item["recommendations"][0]["requirement"]["content"] in snapshots[0]["text"]


def test_requirements_are_lazy_loaded_inside_their_source_entry():
    initial = render(action="sources")
    assert not any("/api/requirements" in path for path in initial["reads"])
    opened = render(action="source_requirements")
    requests = [path for path in opened["reads"] if "/api/requirements" in path]
    assert requests == ["/api/requirements?source_id=alphaxiv"]
    assert "本来源还没有推荐要求" in opened["sources"]["text"]
    assert "填写这个推荐源对应的要求" not in opened["sources"]["text"]
    assert opened["posts"] == []


def test_ingestion_history_is_a_row_per_record_with_status_and_full_details():
    records = [
        {"title": "A long paper title " * 20, "status": "completed", "item_key": "1234ABCD",
         "collection": {"name": "Selected collection"}, "completed_at": "2026-11-09T00:00:00Z"},
        {"title": "<script>ordinary title text</script>", "status": "needs_attention",
         "error": "Provider unavailable", "updated_at": "2026-11-09T01:00:00Z"},
    ]
    result = render(action="history", history=records)
    rows = nodes(result["history"], "history-row")
    assert len(rows) == 2
    for row, record in zip(rows, records):
        assert row["tag"] == "details"
        summary = row["children"][0]
        assert summary["tag"] == "summary"
        assert record["title"] in summary["text"]
        assert "完成范围" not in summary["text"]
        assert "PDF 与 Vault 归档另行处理" in row["children"][1]["text"]
    assert "需要处理" in rows[1]["children"][0]["text"]
    assert "Provider unavailable" in rows[1]["children"][1]["text"]
    assert not result["posts"]


def test_empty_ingestion_history_remains_a_clear_empty_state():
    result = render(action="history", history=[])
    assert "还没有入库记录" in result["history"]["text"]
    assert nodes(result["history"], "history-row") == []


def test_confirmed_review_has_an_explicit_exit_with_exact_current_revision():
    original = candidate(ingestion={"status": "completed", "item_key": "1234ABCD"})
    before = render(action="detail", candidate=original, profile="personal")
    assert nodes(before["detail"], "review")[0]["children"][0]["disabled"]
    assert nodes(before["detail"], "review-revoke")[0]["text"] == "撤销审阅"
    assert "取消待入库选择" in before["detail"]["text"] and "已入库书目保留" in before["detail"]["text"]
    result = render(action="revoke", candidate=original, profile="personal")
    assert result["posts"] == [{"path": "/api/reviews/revoke", "body": {
        "candidate_id": original["candidate_id"], "expected_revision": 3}}]
    assert not nodes(result["detail"], "review-revoke")
    assert not nodes(result["detail"], "review")[0]["children"][0]["disabled"]
    assert nodes(result["detail"], "ingestion-open")[0]["disabled"]
    assert "已选入库" not in result["feed"]["text"]
    assert "书目已入库" in result["detail"]["text"]


@pytest.mark.parametrize("action,message", [("revoke_conflict", "发生变化"), ("revoke_error", "暂时无法完成")])
def test_revoke_failure_keeps_review_and_selection_without_fabricating_success(action, message):
    result = render(action=action)
    assert message in result["detail_notice"]
    assert nodes(result["detail"], "review-revoke")
    assert not nodes(result["detail"], "review-revoke")[0]["disabled"]
    assert not nodes(result["detail"], "ingestion-open")[0]["disabled"]
    assert "已选入库" in result["feed"]["text"]
    assert len(result["posts"]) == 1


def test_in_progress_ingestion_disables_review_withdrawal_only_until_finished():
    result = render(action="detail", candidate=candidate(ingestion={"status": "in_progress"}))
    assert nodes(result["detail"], "review-revoke")[0]["disabled"]
    assert "正在入库，完成后才能撤销审阅" in result["detail"]["text"]
    assert result["posts"] == []


@pytest.mark.parametrize("profile", ["test", "personal"])
def test_ingestion_actions_state_simulation_or_real_bibliography_scope(profile):
    result = render(action="plan", profile=profile)
    button = nodes(result["detail"], "ingestion-open")[0]
    execute = nodes(result["plan"], "ingestion-execute")[0]
    if profile == "test":
        assert "模拟书目入库" in button["text"] and "模拟书目入库" in result["dialog_title"]
        assert "模拟" in execute["text"]
        assert "不写入真实 Zotero" in result["plan"]["text"]
    else:
        assert button["text"] == "预览 Zotero 书目入库"
        assert execute["text"] == "确认 Zotero 书目入库"
        assert "本次加入 Zotero 书目" in result["plan"]["text"]
        assert "模拟" not in result["plan"]["text"]
    assert "不表示 PDF 已保存或 Vault 知识单元已建立" in result["plan"]["text"]
    assert not any(post["path"] == "/api/ingestion/execute" for post in result["posts"])


@pytest.mark.parametrize("profile", ["test", "personal"])
def test_history_page_distinguishes_simulated_records_from_real_zotero_writes(profile):
    result = render(action="history", profile=profile)
    explanation = "测试记录为模拟结果，不代表资料已写入真实 Zotero。"
    assert (explanation in result["history_scope"]["text"]) == (profile == "test")
    assert "PDF 附件和 Vault 知识单元" in result["history_scope"]["text"]


def test_fresh_plain_url_windows_initialize_without_saved_credentials():
    for _ in range(2):
        result = render(action="initial")
        assert result["initial"]["children"]
        assert len(result["sessions"]) == 1
        session = result["sessions"][0]
        assert session["method"] == "POST" and session["body"] == "{}"
        assert session["headers"]["X-Scholar-Client"] == "recommendation-page"
        assert "scholar-recommendations-session" not in result["storage"]
        assert not result["posts"]


def test_bootstrap_failure_never_loads_recommendation_data():
    result = render(action="initial", session_failure=True)
    assert not result["initial"]["children"]
    assert not any(path.startswith("/api/candidates") for path in result["reads"])



def test_manual_tag_picker_add_reset_and_undo():
    result = render(action="tags_save")
    assert result["posts"] == [{"path": "/api/tags", "body": {
        "candidate_id": candidate()["candidate_id"], "expected_revision": 3,
        "tags": [*candidate()["tags"], "场景编排"]}}]
    reset = render(action="tags_reset")
    assert reset["posts"][0]["path"] == "/api/tags/reset"
    undone = render(action="tags_undo")
    assert len(undone["posts"]) == 2
    assert undone["posts"][1]["body"]["expected_revision"] == 4
    assert undone["posts"][1]["body"]["tags"] == candidate()["tags"]


def test_manual_tag_picker_conflict_keeps_input_and_original_chips():
    result = render(action="tags_conflict")
    assert nodes(result["detail"], "tag-search")[0]["value"] == "场景编排"
    assert "输入和原标签已保留" in result["detail"]["text"]
    assert nodes(result["detail"], "tag-chip")


def test_manual_tag_picker_search_and_escape_do_not_write():
    searched = render(action="tags_search")
    assert not searched["posts"]
    assert "创建“场景编排”" in searched["detail"]["text"]
    escaped = render(action="tags_escape")
    assert not escaped["posts"]
    assert not nodes(escaped["detail"], "tag-picker")[0]["open"]


def test_manual_tag_picker_removes_only_selected_association():
    result = render(action="tags_remove")
    assert result["posts"][0]["body"]["tags"] == candidate()["tags"][1:]


def test_tag_picker_existing_label_and_closed_picker_undo():
    result = render(action="tags_existing")
    assert result["posts"][0]["body"]["tags"] == ["world-models"]
    result = render(action="tags_closed_undo")
    assert len(result["posts"]) == 2
    assert result["posts"][1]["body"]["tags"] == candidate()["tags"]


def test_quality_rejection_has_its_own_visible_status():
    result = render(action="details", candidate=candidate(decision="ignored", disposition={"reason": "quality", "scope": None}))
    assert "质量不符合要求 · 处理已记录" in result["detail"]["text"]
    panels = nodes(result["detail"], "rejection-picker")
    assert len(panels) == 1
    assert "质量不符合要求" not in panels[0]["text"]
    assert "不是当前想关注的方向" in panels[0]["text"]
    assert "其他" in panels[0]["text"]
    assert "恢复未处理" not in panels[0]["text"]
