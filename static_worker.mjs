import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.8/full/pyodide.mjs";

async function initialize() {
  const python = await loadPyodide();
  python.FS.mkdir("/koushougi");
  python.FS.mkdir("/koushougi/players");
  const files = [
    "__init__.py", "board.py", "game.py", "position.py", "kifu.py", "evaluation.py", "value_network.py",
    "move_ordering.py", "search.py", "players/__init__.py", "players/alpha_beta.py",
  ];
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
from koushougi.kifu import replay_record

def browser_position(request):
    move_history, opponent, human_side, operation = json.loads(request)
    if operation == "record":
        return json.dumps(replay_record(move_history))
    return json.dumps(position(move_history, ai=opponent, human_side=human_side))
`);
  return python.globals.get("browser_position");
}

let ready;
self.onmessage = async ({data}) => {
  const {id, history, opponent, humanSide, operation} = data;
  try {
    ready ??= initialize();
    const position = await ready;
    const state = JSON.parse(position(JSON.stringify([history, opponent, humanSide, operation ?? "position"])));
    self.postMessage({id, state});
  } catch (error) {
    self.postMessage({id, error: String(error)});
  }
};
