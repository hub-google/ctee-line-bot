import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
const source=readFileSync(new URL("./worker.js",import.meta.url),"utf8");
globalThis.crypto ||= webcrypto;
const {default:worker}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
class MemoryKV {
  records=new Map();
  async get(key,type){const v=this.records.get(key);return !v?null:type==="json"?JSON.parse(v):v}
  async put(key,value){this.records.set(key,value)}
  async list({prefix,limit}){const keys=[...this.records.keys()].filter(k=>k.startsWith(prefix)).slice(0,limit).map(name=>({name}));return{keys,list_complete:true}}
}
const kv=new MemoryKV(),env={INBOX:kv,CTEE_ADMIN_PIN:"9"};
const origin="https://hub-google.github.io";
const requestId="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
function req(path,method="GET",body,pin,siteOrigin=origin){
  const headers={"Origin":siteOrigin,"CF-Connecting-IP":"198.51.100.17"};
  if(body!==undefined)headers["Content-Type"]="application/json";
  if(pin!==undefined)headers["X-CTEE-Admin-Pin"]=pin;
  return new Request("https://example.workers.dev"+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
}
async function call(path,method="GET",body,pin,siteOrigin){
  const res=await worker.fetch(req(path,method,body,pin,siteOrigin),env);
  return{status:res.status,json:res.status===204?null:await res.json()};
}
const payload={request_id:requestId,name:"測試使用者",reason:"獨立項目測試",items:[
  {operation:"add",keyword:"test1"},
  {operation:"add",keyword:"test2"},
  {operation:"remove",keyword:"test3"}
]};
const preflight=await call("/", "OPTIONS");
assert.equal(preflight.status,204);
const blocked=await call("/submit","POST",payload,undefined,"https://attacker.example");
assert.equal(blocked.status,403);
const created=await call("/submit","POST",payload);
assert.equal(created.status,201);
assert.equal(created.json.count,3);
const repeat=await call("/submit","POST",payload);
assert.equal(repeat.status,201);
const invalidPin=await call("/reviews","GET",undefined,"wrong");
assert.equal(invalidPin.status,401);
const initial=await call("/reviews","GET",undefined,"9");
assert.equal(initial.json.items.length,3);
const [i1,i2,i3]=initial.json.items.sort((a,b)=>a.id.localeCompare(b.id));
assert.deepEqual([i1.keyword,i2.keyword,i3.keyword],["test1","test2","test3"]);
const first=await call("/review","POST",{id:i1.id,decision:"approved"},"9");
assert.equal(first.status,200);
const second=await call("/review","POST",{id:i2.id,decision:"rejected"},"9");
assert.equal(second.status,200);
const repeatedDecision=await call("/review","POST",{id:i1.id,decision:"approved"},"9");
assert.equal(repeatedDecision.status,409);
const updated=await call("/reviews","GET",undefined,"9");
const result=new Map(updated.json.items.map(x=>[x.keyword,x.status]));
assert.equal(result.get("test1"),"approved");
assert.equal(result.get("test2"),"rejected");
assert.equal(result.get("test3"),"pending");
const exportResult=await call("/export");
assert.equal(exportResult.json.items.length,2);
assert.ok(exportResult.json.items.every(x=>!Object.hasOwn(x,"name")));
console.log("CTEE keyword gateway tests passed: anonymous submit, no GitHub login, unique requests, independent review, export, origin restriction, admin PIN.");
