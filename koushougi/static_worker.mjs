import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.8/full/pyodide.mjs";

async function initialize() {
  const python = await loadPyodide();
  python.FS.mkdir("/koushougi");
  const files = ["__init__.py", "game.py", "ai.py", "position.py"];
  await Promise.all(files.map(async name => {
    const response = await fetch(new URL("./koushougi/" + name, import.meta.url));
    if (!response.ok) throw new Error("Failed to load " + name);
    python.FS.writeFile("/koushougi/" + name, await response.text());
  }));
  python.runPython(`
import json
import sys
sys.path.insert(0, "/")
from koushougi.position import position

def browser_position(request):
    move_history, opponent, human_side = json.loads(request)
    return json.dumps(position(move_history, ai=opponent, human_side=human_side))
`);
  return python.globals.get("browser_position");
}

let ready;
self.onmessage = async ({data}) => {
  const {id, history, opponent, humanSide} = data;
  try {
    ready ??= initialize();
    const position = await ready;
    const state = JSON.parse(position(JSON.stringify([history, opponent, humanSide])));
    self.postMessage({id, state});
  } catch (error) {
    self.postMessage({id, error: String(error)});
  }
};
