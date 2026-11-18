"""One-off CTEE Supabase end-to-end verification; creates and removes its own test keyword."""
import json
import uuid
import urllib.request

API = "https://unapiwajmgqqtdkixaab.supabase.co/functions/v1/ctee-keywords"
ORIGIN = "https://hub-google.github.io"
TEST_PIN = "9"

def call(data=None):
    payload=None if data is None else json.dumps(data,ensure_ascii=False).encode("utf-8")
    headers={"Origin":ORIGIN,"Accept":"application/json"}
    if data is not None:headers["Content-Type"]="application/json"
    with urllib.request.urlopen(urllib.request.Request(API,payload,headers),timeout=30) as response:
        body=json.load(response)
        assert response.headers.get("Access-Control-Allow-Origin")==ORIGIN
        assert body.get("ok") is True,body
        return body

def main():
    marker=uuid.uuid4().hex[:10].upper()
    first="CTEE_E2E_ADD_"+marker
    second="CTEE_E2E_REJECT_"+marker
    before=call()["keywords"]
    assert "凱壽" in before and first not in before and second not in before
    batch=uuid.uuid4()
    result=call({"action":"submit","request_id":str(batch),"name":"CTEE自動驗收","reason":"一次性核准、駁回測試",
        "items":[{"operation":"add","keyword":first},
                 {"operation":"add","keyword":second},
                 {"operation":"remove","keyword":"凱壽"}]})
    assert result["count"]==3,result
    check=call({"action":"admin-list","pin":TEST_PIN})
    items=[x for x in check["items"] if x["batch_id"]==str(batch)]
    assert len(items)==3,items
    ids={(x["operation"],x["word"]):x["id"] for x in items}
    yes=call({"action":"review","pin":TEST_PIN,"id":ids[("add",first)],"decision":"approved"})
    assert yes["synced"] is True and first in yes["keywords"],yes
    no1=call({"action":"review","pin":TEST_PIN,"id":ids[("add",second)],"decision":"rejected"})
    no2=call({"action":"review","pin":TEST_PIN,"id":ids[("remove","凱壽")],"decision":"rejected"})
    assert no1["synced"] and no2["synced"]
    intermediate=call()["keywords"]
    assert first in intermediate and second not in intermediate and "凱壽" in intermediate
    cleanup_batch=uuid.uuid4()
    result=call({"action":"submit","request_id":str(cleanup_batch),"name":"CTEE自動驗收","reason":"清理驗收關鍵字",
        "items":[{"operation":"remove","keyword":first}]})
    assert result["count"]==1
    pending=call({"action":"admin-list","pin":TEST_PIN})
    cleanup=[x for x in pending["items"] if x["batch_id"]==str(cleanup_batch)]
    assert len(cleanup)==1,cleanup
    done=call({"action":"review","pin":TEST_PIN,"id":cleanup[0]["id"],"decision":"approved"})
    assert done["synced"] is True
    final=call()["keywords"]
    assert first not in final and second not in final and "凱壽" in final
    assert len(final)==len(before)
    print("CTEE_E2E_PASS: anonymous batch submission, per-item approve/reject, immediate updates, keyword cleanup; total",len(final))

if __name__=="__main__":
    main()
