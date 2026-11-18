import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";

const source=readFileSync(new URL("./worker.js",import.meta.url),"utf8");
globalThis.crypto ||= webcrypto;
const {default:worker}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));

class MemoryKV {
  records=new Map();
  async get(key,type){
    const value=this.records.get(key);
    return value===undefined?null:type==="json"?JSON.parse(value):value;
  }
  async put(key,value){this.records.set(key,value)}
  async list({prefix,limit}){
    const keys=[...this.records.keys()].filter(k=>k.startsWith(prefix)).slice(0,limit).map(name=>({name}));
    return {keys,list_complete:true};
  }
}
const kv=new MemoryKV(),env={INBOX:kv,CTEE_ADMIN_PIN:"9"};
const origin="https://hub-google.github.io";
const requestId="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
function req(path,method="GET",body,pin,siteOrigin=origin){
  const headers={"Origin":siteOrigin,"CF-Connecting-IP":"198.51.100.17"};
  if(body!==undefined)headers["Content-Type"]="application/json";
  if(pin!==undefined)headers["X-CTEE-Admin-Pin"]=pin;
  return new Request("https://example.workers.dev"+path,{method,headers,
    body:body===undefined?undefined:JSON.stringify(body)});
}
async function call(path,method="GET",body,pin,siteOrigin){
  const res=await worker.fetch(req(path,method,body,pin,siteOrigin),env);
  return {status:res.status,json:res.status===204?null:await res.json()};
}
const payload={request_id:requestId,name:"測試使用者",reason:"獨立項目測試",items:[
  {operation:"add",keyword:"test1"},
  {operation:"add",keyword:"test2"},
  {operation:"remove",keyword:"test3"}
]};
assert.equal((await call("/","OPTIONS")).status,204);
assert.equal((await call("/submit","POST",payload,undefined,"https://attacker.example")).status,403);
assert.equal((await call("/submit","POST",payload)).status,201);
assert.equal((await call("/submit","POST",payload)).status,201);
assert.equal((await call("/reviews","GET",undefined,"wrong")).status,401);
const initial=await call("/reviews","GET",undefined,"9");
assert.equal(initial.json.items.length,3);
const [i1,i2,i3]=initial.json.items.sort((a,b)=>a.id.localeCompare(b.id));
assert.deepEqual([i1.keyword,i2.keyword,i3.keyword],["test1","test2","test3"]);

const unavailable=await call("/review","POST",{id:i1.id,decision:"approved"},"9");
assert.equal(unavailable.status,503,"Without GitHub credential it must NOT claim successful approval");
assert.equal((await call("/reviews","GET",undefined,"9")).json.items.find(x=>x.id===i1.id).status,"pending");

const originalFetch=globalThis.fetch;
let remote=["test3"],revision=0,getCount=0,putCount=0;
globalThis.fetch=async (url,init={})=>{
  assert.ok(String(url).startsWith("https://api.github.com/repos/hub-google/ctee-line-bot/contents/keywords.txt"));
  assert.equal(init.headers.Authorization,"Bearer TEST_ONLY_FAKE_TOKEN");
  if(init.method==="GET"){
    getCount++;
    return new Response(JSON.stringify({
      sha:"sha"+revision,
      content:Buffer.from(remote.join("\n")+"\n","utf8").toString("base64")
    }),{status:200,headers:{"Content-Type":"application/json"}});
  }
  assert.equal(init.method,"PUT");
  const body=JSON.parse(init.body);
  assert.equal(body.sha,"sha"+revision);
  assert.equal(body.branch,"master");
  remote=Buffer.from(body.content,"base64").toString("utf8").trim().split("\n");
  revision++;putCount++;
  return new Response(JSON.stringify({commit:{sha:"commit"+revision},content:{sha:"sha"+revision}}),
    {status:200,headers:{"Content-Type":"application/json"}});
};
env.GITHUB_WRITE_TOKEN="TEST_ONLY_FAKE_TOKEN";
try {
  const first=await call("/review","POST",{id:i1.id,decision:"approved"},"9");
  assert.equal(first.status,200);
  assert.equal(first.json.synced,true);
  assert.equal(first.json.commit,"commit1");
  assert.ok(first.json.keywords.includes("test1"));
  assert.ok(remote.includes("test1"));
  assert.equal(putCount,1);
  const second=await call("/review","POST",{id:i2.id,decision:"rejected"},"9");
  assert.equal(second.status,200);
  assert.equal(second.json.synced,false);
  assert.equal(putCount,1,"Rejecting an item must not write to GitHub");
  assert.equal((await call("/review","POST",{id:i1.id,decision:"approved"},"9")).status,409);
  const records=await call("/reviews","GET",undefined,"9");
  const decisions=new Map(records.json.items.map(x=>[x.keyword,x.status]));
  assert.equal(decisions.get("test1"),"approved");
  assert.equal(decisions.get("test2"),"rejected");
  assert.equal(decisions.get("test3"),"pending");
  const exportResult=await call("/export");
  assert.equal(exportResult.json.items.length,2);
  assert.ok(exportResult.json.items.every(x=>!Object.hasOwn(x,"name")));
  assert.ok(getCount>=1);
} finally {globalThis.fetch=originalFetch}
console.log("CTEE gateway: anonymous submit, PIN review, no 20-second polling, direct GitHub approval, rejection isolation, no approval without GitHub credentials — PASS");
