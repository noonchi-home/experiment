from pathlib import Path
import json, os, sys, urllib.request, urllib.error

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None

folder = Path(__file__).resolve().parent
scene = sys.argv[1]
request = (folder / (scene + "_request.json")).read_bytes()
out = folder / (scene + "_response.json")
if out.exists():
    raise SystemExit("Existing response; not overwriting")
req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=request, headers={"Authorization":"Bearer " + os.environ["OPENROUTER_API_KEY"], "Content-Type":"application/json"})
with urllib.request.build_opener(NoRedirect()).open(req, timeout=300) as stream:
    data = json.load(stream)
if "error" in data:
    raise SystemExit(str(data["error"].get("message","provider error"))[:250])
choice = data["choices"][0]
content = choice["message"].get("content")
record = {"id":data.get("id"), "model":data.get("model"),"provider":data.get("provider"),"usage":data.get("usage"),"finish_reason":choice.get("finish_reason"),"content":content}
out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
if not isinstance(content, str) or choice.get("finish_reason") != "stop":
    raise SystemExit("Incomplete content")
(folder / (scene+"_content.txt")).write_bytes(content.encode("utf-8"))
print(scene, data["id"], choice["finish_reason"], data.get("usage",{}).get("cost"))

