import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function settingsRow() {
  const row = document.createElement("tr");
  const name = document.createElement("td");
  name.textContent = "Kotodama connection";
  const value = document.createElement("td");
  const status = document.createElement("div");
  status.textContent = "Loading…";
  const testResult = document.createElement("div");
  const help = document.createElement("div");
  help.textContent = "Set the endpoint and optional key in the shown .env path, then refresh. See Kotodama's README.";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Test connection";

  async function refresh() {
    try {
      const response = await api.fetchApi("/kotodama/status");
      if (!response.ok) throw new Error("status unavailable");
      const data = await response.json();
      status.textContent = `URL: ${data.url || "not configured"} (from ${data.source?.url || "none"}) · key: ${data.key_set ? "set" : "not set"} (from ${data.source?.key || "none"}) · config: ${data.config_path}`;
    } catch {
      status.textContent = "Kotodama status unavailable; check the server log.";
    }
  }

  button.addEventListener("click", async () => {
    button.disabled = true;
    testResult.textContent = "Testing saved configuration…";
    try {
      const response = await api.fetchApi("/kotodama/test", { method: "POST" });
      const data = await response.json();
      testResult.textContent = response.status === 429
        ? "Please wait five seconds before testing again."
        : data.ok ? `Connected (HTTP ${data.status}).` : `Connection failed: ${data.error || "unknown"}${data.status ? ` (HTTP ${data.status})` : ""}.`;
    } catch {
      testResult.textContent = "Connection test unavailable; check the server log.";
    } finally {
      button.disabled = false;
    }
  });

  value.append(status, help, button, testResult);
  row.append(name, value);
  void refresh();
  return row;
}

app.registerExtension({
  name: "Kotodama.ConnectionStatus",
  setup() {
    app.ui.settings.addSetting({
      id: "Kotodama.ConnectionStatus",
      name: "Kotodama connection",
      type: settingsRow,
      defaultValue: null,
    });
  },
});
