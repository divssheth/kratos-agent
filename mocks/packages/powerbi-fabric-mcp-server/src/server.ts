#!/usr/bin/env node
// powerbi-fabric-mcp-server - MCP scaffold for semantic-model-first NL->DAX flow.
// This intentionally avoids storing credentials and requires a short-lived
// delegated access token via POWERBI_ACCESS_TOKEN.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

type Workspace = {
  id: string;
  name: string;
};

type SemanticModel = {
  id: string;
  workspaceId: string;
  name: string;
};

type SchemaPayload = {
  workspaceId: string;
  modelId: string;
  tables: Array<{ name: string; columns: string[] }>;
  measures: Array<{ name: string; expression: string }>;
};

const DEFAULT_WORKSPACES: Workspace[] = [
  { id: "ws-001", name: "Finance Workspace" },
  { id: "ws-002", name: "Sales Workspace" },
];

const DEFAULT_MODELS: SemanticModel[] = [
  { id: "sm-finance-001", workspaceId: "ws-001", name: "Finance Close Model" },
  { id: "sm-sales-001", workspaceId: "ws-002", name: "Sales Review Model" },
];

const DEFAULT_SCHEMAS: SchemaPayload[] = [
  {
    workspaceId: "ws-001",
    modelId: "sm-finance-001",
    tables: [
      { name: "Date", columns: ["Date", "Month", "Quarter", "Year"] },
      { name: "Ledger", columns: ["Entity", "Account", "Amount", "PostingDate"] },
    ],
    measures: [
      { name: "Total Amount", expression: "SUM(Ledger[Amount])" },
      { name: "YTD Amount", expression: "TOTALYTD([Total Amount], Date[Date])" },
    ],
  },
  {
    workspaceId: "ws-002",
    modelId: "sm-sales-001",
    tables: [
      { name: "Date", columns: ["Date", "Month", "Quarter", "Year"] },
      { name: "Opportunities", columns: ["Region", "Stage", "Amount", "CloseDate"] },
    ],
    measures: [
      { name: "Pipeline", expression: "SUM(Opportunities[Amount])" },
      { name: "Won Revenue", expression: "CALCULATE([Pipeline], Opportunities[Stage] = \"Closed Won\")" },
    ],
  },
];

function parseJsonEnv<T>(key: string, fallback: T): T {
  const value = process.env[key];
  if (!value) {
    return fallback;
  }
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

function ensureDelegatedToken() {
  const token = process.env.POWERBI_ACCESS_TOKEN;
  if (!token || token.trim().length < 20) {
    return {
      ok: false,
      error: {
        error: "missing_token",
        message:
          "POWERBI_ACCESS_TOKEN is missing. This server requires a short-lived delegated access token.",
      },
    };
  }
  return { ok: true, token };
}

function text(obj: unknown) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(obj, null, 2) }],
  };
}

function toolError(code: string, message: string) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify({ error: code, message }, null, 2) }],
    isError: true,
  };
}

const server = new McpServer({
  name: "powerbi-fabric-mcp-server",
  version: "0.1.0",
});

const workspaces = parseJsonEnv<Workspace[]>("FABRIC_MOCK_WORKSPACES_JSON", DEFAULT_WORKSPACES);
const models = parseJsonEnv<SemanticModel[]>("FABRIC_MOCK_MODELS_JSON", DEFAULT_MODELS);
const schemas = parseJsonEnv<SchemaPayload[]>("FABRIC_MOCK_SCHEMAS_JSON", DEFAULT_SCHEMAS);

server.registerTool(
  "fabric_list_workspaces",
  {
    title: "List Fabric workspaces",
    description: "List workspaces accessible to the current delegated user context.",
    inputSchema: {},
  },
  async () => {
    const auth = ensureDelegatedToken();
    if (!auth.ok) return text(auth.error);
    return text({ workspaces, authMode: "user_obo" });
  }
);

server.registerTool(
  "fabric_list_semantic_models",
  {
    title: "List semantic models in workspace",
    description: "Return semantic models in a selected workspace.",
    inputSchema: {
      workspace_id: z.string().min(1),
    },
  },
  async ({ workspace_id }) => {
    const auth = ensureDelegatedToken();
    if (!auth.ok) return text(auth.error);

    const workspaceExists = workspaces.some((w) => w.id === workspace_id);
    if (!workspaceExists) {
      return toolError("workspace_not_found", `Workspace '${workspace_id}' does not exist or is not accessible.`);
    }

    return text({
      workspace_id,
      models: models.filter((m) => m.workspaceId === workspace_id),
      authMode: "user_obo",
    });
  }
);

server.registerTool(
  "fabric_get_semantic_model_schema",
  {
    title: "Get semantic model schema",
    description: "Get tables, columns, and measures for semantic-model-first query generation.",
    inputSchema: {
      workspace_id: z.string().min(1),
      model_id: z.string().min(1),
    },
  },
  async ({ workspace_id, model_id }) => {
    const auth = ensureDelegatedToken();
    if (!auth.ok) return text(auth.error);

    const schema = schemas.find((s) => s.workspaceId === workspace_id && s.modelId === model_id);
    if (!schema) {
      return toolError(
        "schema_not_found",
        `Schema not found for workspace '${workspace_id}' and model '${model_id}'.`
      );
    }

    return text({ schema, guidance: "Generate DAX only from discovered schema entities." });
  }
);

server.registerTool(
  "fabric_generate_dax_from_nl",
  {
    title: "Generate DAX from natural language",
    description: "Generate a constrained DAX draft using supplied schema context.",
    inputSchema: {
      question: z.string().min(3),
      schema_context: z.string().min(3),
    },
  },
  async ({ question }) => {
    const auth = ensureDelegatedToken();
    if (!auth.ok) return text(auth.error);

    const dax = [
      "EVALUATE",
      "SUMMARIZECOLUMNS(",
      "  Date[Month],",
      '  \"Value\", [Total Amount]',
      ")",
      "ORDER BY Date[Month]",
    ].join("\n");

    return text({
      question,
      dax,
      notes: [
        "Draft generated from semantic-model-first flow.",
        "Validate against the model before execution.",
      ],
    });
  }
);

server.registerTool(
  "fabric_validate_or_explain_dax",
  {
    title: "Validate or explain DAX",
    description: "Basic validation pass before query execution.",
    inputSchema: {
      workspace_id: z.string().min(1),
      model_id: z.string().min(1),
      dax_query: z.string().min(10),
    },
  },
  async ({ dax_query }) => {
    const auth = ensureDelegatedToken();
    if (!auth.ok) return text(auth.error);

    const hasEvaluate = /\bEVALUATE\b/i.test(dax_query);
    if (!hasEvaluate) {
      return text({
        is_valid: false,
        error: "DAX query must include EVALUATE.",
        suggested_fix: "Prefix query with EVALUATE and return a table expression.",
      });
    }

    return text({ is_valid: true, warnings: [] });
  }
);

server.registerTool(
  "fabric_query_semantic_model",
  {
    title: "Query semantic model",
    description:
      "Execute DAX query against semantic model. Returns query-limit metadata for user warnings.",
    inputSchema: {
      workspace_id: z.string().min(1),
      model_id: z.string().min(1),
      dax_query: z.string().min(10),
      limit: z.number().int().min(1).max(5000).optional(),
    },
  },
  async ({ workspace_id, model_id, dax_query, limit }) => {
    const auth = ensureDelegatedToken();
    if (!auth.ok) return text(auth.error);

    const effectiveLimit = limit ?? 1000;
    const rows = Array.from({ length: Math.min(effectiveLimit, 3) }).map((_, i) => ({
      workspace_id,
      model_id,
      month: `2026-${String(i + 1).padStart(2, "0")}`,
      value: 1000 * (i + 1),
    }));

    const rowLimit = 1000;
    const wasTruncated = effectiveLimit > rowLimit;

    return text({
      dax_query,
      rows,
      limit_metadata: {
        rows_returned: rows.length,
        row_limit: rowLimit,
        duration_ms: 120,
        was_truncated: wasTruncated,
      },
      warnings: wasTruncated ? ["Result truncated due to row_limit."] : [],
      authMode: "user_obo",
    });
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  process.stderr.write(`${String(error)}\n`);
  process.exit(1);
});
