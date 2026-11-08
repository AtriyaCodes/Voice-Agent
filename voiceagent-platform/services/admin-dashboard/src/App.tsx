import { useState } from "react";

/**
 * Placeholder shell for the ops console. Real views (live call monitor,
 * tenant configuration editor, transcript QA) each call orchestration-api
 * and are intentionally not fleshed out here; this file exists so the
 * service boots and the routing/layout skeleton has one obvious place to
 * grow from.
 */
export default function App() {
  const [tenantId] = useState<string>("");

  return (
    <div>
      <h1>VoiceAgent Ops Console</h1>
      <p>Tenant: {tenantId || "not selected"}</p>
    </div>
  );
}
