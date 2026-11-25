import json

from readnet.store import Store

s = Store("e2e.db")
print(json.dumps(s.stats(), indent=1))
for f in s.flows():
    print(
        "FLOW",
        f["id"],
        f["process"],
        f["remote_addr"],
        f["remote_port"],
        f["out_bytes"],
        f["in_bytes"],
        f["host"],
    )
    d = s.flow_detail(f["id"])
    p = d["parsed"]
    print(" parsed:", p["parsed_source"], p["request_count"], p["response_count"])
    for x in p["exchanges"]:
        rq = x.get("request") or {}
        rs = x.get("response") or {}
        print(
            "  ->",
            rq.get("method"),
            rq.get("target"),
            "|",
            rs.get("status"),
            (rs.get("headers_dict") or {}).get("content-type"),
        )
s.close()
