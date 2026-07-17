import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const services = [
  {
    name: "agentic",
    command: resolve(root, ".venv/bin/uvicorn"),
    args: ["main:app", "--reload", "--host", "127.0.0.1", "--port", "9000"],
    cwd: root,
  },
  {
    name: "interaction",
    command: resolve(root, ".venv/bin/uvicorn"),
    args: ["app.main:app", "--reload", "--host", "127.0.0.1", "--port", "8001"],
    cwd: resolve(root, "VoiceAssistant_Nafea/backend"),
    env: { ...process.env, PYTHONPATH: "." },
  },
  {
    name: "web",
    command: resolve(root, "node_modules/.bin/next"),
    args: ["dev"],
    cwd: root,
    env: { ...process.env, NEXT_DIST_DIR: ".next-dev" },
  },
];

let stopping = false;
const children = services.map((service) => {
  const child = spawn(service.command, service.args, {
    cwd: service.cwd,
    env: service.env ?? process.env,
    stdio: "inherit",
  });
  child.on("error", (error) => {
    console.error(`[${service.name}] failed to start: ${error.message}`);
  });
  child.on("exit", (code, signal) => {
    if (stopping) return;
    console.error(
      `[${service.name}] stopped unexpectedly (${signal ?? `exit ${code ?? 1}`}); stopping the dev stack.`
    );
    shutdown("SIGTERM", code ?? 1);
  });
  return child;
});

function shutdown(signal, exitCode = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) {
    if (child.exitCode === null && child.signalCode === null) child.kill(signal);
  }
  const timer = setTimeout(() => process.exit(exitCode), 3_000);
  timer.unref();
  Promise.allSettled(
    children.map(
      (child) =>
        new Promise((resolveChild) => {
          if (child.exitCode !== null || child.signalCode !== null) resolveChild();
          else child.once("exit", resolveChild);
        })
    )
  ).then(() => process.exit(exitCode));
}

process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));
