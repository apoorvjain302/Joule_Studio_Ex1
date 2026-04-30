#!/bin/bash
set -euo pipefail

echo "=== Building pallet-verification-ui ==="

# Install all deps (dev included) for build tools only
echo "--- Installing all dependencies ---"
cd /app
npm install --legacy-peer-deps --ignore-scripts

# Build the React UI from ui/ directory (vite.config.js sets outDir=../app)
echo "--- Building React UI ---"
cd /app/ui
/app/node_modules/.bin/vite build

OUTPUT_DIR="${OUTPUT_PATH:-/outputs}"
echo "--- Copying build output to ${OUTPUT_DIR} ---"

# Create output structure
mkdir -p "${OUTPUT_DIR}/app"

# Copy React static build to /outputs/app/
if [ -d /app/app ] && [ "$(ls -A /app/app 2>/dev/null)" ]; then
  cp -r /app/app/. "${OUTPUT_DIR}/app/"
  echo "Copied React static files"
fi

# Write a minimal package.json for the runtime (only lists @sap/cds for node_modules)
cat > "${OUTPUT_DIR}/package.json" << 'PKGJSON'
{
  "name": "pallet-verification-ui-runtime",
  "version": "1.0.0",
  "private": true,
  "dependencies": {
    "@sap/cds": "^9"
  }
}
PKGJSON

# Write the standalone Node.js HTTP server.
# This replaces the CDS server entirely — no DB needed, no CDS startup issues.
# Handles: /health, /api/verify (proxy to AI agent), static files.
cat > "${OUTPUT_DIR}/server.js" << 'SERVERJS'
"use strict";
const http = require("http");
const https = require("https");
const fs = require("fs");
const path = require("path");

const PORT = 4004;
const STATIC_DIR = path.join(__dirname, "app");

// AI Agent URL - injected by deployer or env
const AGENT_URL = process.env.AGENT_URL || "https://4d4023fb-454da2c5.cf54612.stage.kyma.ondemand.com";

// MIME type map for static files
const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js":   "application/javascript; charset=utf-8",
  ".css":  "text/css; charset=utf-8",
  ".json": "application/json",
  ".png":  "image/png",
  ".jpg":  "image/jpeg",
  ".svg":  "image/svg+xml",
  ".ico":  "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf":  "font/ttf",
  ".map":  "application/json",
};

function serveFile(filePath, res) {
  fs.readFile(filePath, (err, data) => {
    if (err) return serveIndex(res);
    const ext = path.extname(filePath);
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
    res.end(data);
  });
}

function serveIndex(res) {
  const indexPath = path.join(STATIC_DIR, "index.html");
  fs.readFile(indexPath, (err, data) => {
    if (err) {
      res.writeHead(404, { "Content-Type": "text/plain" });
      res.end("Not found");
      return;
    }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(data);
  });
}

function proxyVerify(reqBody, res) {
  let payload;
  try {
    const params = JSON.parse(reqBody);
    const { deliveryOrder, imageUrl, channel } = params;

    const userText = [
      `Verify pallet for EWM outbound delivery order: ${deliveryOrder}.`,
      `Image: ${imageUrl}`,
      `Channel: ${channel || "web"}`,
    ].join("\n");

    payload = JSON.stringify({
      jsonrpc: "2.0",
      method: "message/send",
      id: Date.now(),
      params: {
        message: {
          role: "user",
          parts: [{ kind: "text", text: userText }],
        },
      },
    });
  } catch (e) {
    res.writeHead(400, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { message: "Invalid request: " + e.message } }));
    return;
  }

  const agentUrl = new URL(AGENT_URL);
  const isHttps = agentUrl.protocol === "https:";
  const options = {
    hostname: agentUrl.hostname,
    port: agentUrl.port || (isHttps ? 443 : 80),
    path: agentUrl.pathname || "/",
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(payload),
    },
  };

  const mod = isHttps ? https : http;
  const proxyReq = mod.request(options, (proxyRes) => {
    let data = "";
    proxyRes.on("data", (chunk) => (data += chunk));
    proxyRes.on("end", () => {
      if (proxyRes.statusCode !== 200) {
        res.writeHead(502, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ error: { message: `Agent returned ${proxyRes.statusCode}: ${data}` } }));
        return;
      }
      try {
        const agentResp = JSON.parse(data);
        const result =
          agentResp?.result?.message?.parts?.[0]?.text ||
          agentResp?.result?.parts?.[0]?.text ||
          JSON.stringify(agentResp?.result ?? agentResp);
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ value: result }));
      } catch (e) {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ value: data }));
      }
    });
  });

  proxyReq.on("error", (e) => {
    res.writeHead(503, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { message: "Could not reach agent: " + e.message } }));
  });

  proxyReq.setTimeout(120000, () => {
    proxyReq.destroy();
    res.writeHead(504, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: { message: "Agent request timed out" } }));
  });

  proxyReq.write(payload);
  proxyReq.end();
}

const server = http.createServer((req, res) => {
  // CORS headers
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");

  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }

  const urlPath = req.url.split("?")[0];

  // Health check endpoint
  if (urlPath === "/health" || urlPath === "/health/") {
    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ status: "ok", uptime: process.uptime() }));
    return;
  }

  // API: proxy verify action to AI agent
  if (urlPath === "/api/verify" && req.method === "POST") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => proxyVerify(body, res));
    return;
  }

  // Static file serving
  if (req.method === "GET") {
    const cleanPath = urlPath.replace(/\.\./g, "");
    const filePath = path.join(STATIC_DIR, cleanPath);

    fs.access(filePath, fs.constants.R_OK, (err) => {
      if (err) {
        // SPA fallback: serve index.html for all unknown paths
        serveIndex(res);
      } else {
        fs.stat(filePath, (statErr, stat) => {
          if (statErr || stat.isDirectory()) {
            serveIndex(res);
          } else {
            serveFile(filePath, res);
          }
        });
      }
    });
    return;
  }

  res.writeHead(404, { "Content-Type": "application/json" });
  res.end(JSON.stringify({ error: "Not found" }));
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`[pallet-ui] Server listening on port ${PORT}`);
  console.log(`[pallet-ui] Agent URL: ${AGENT_URL}`);
  console.log(`[pallet-ui] Static dir: ${STATIC_DIR}`);
});

server.on("error", (err) => {
  console.error("[pallet-ui] Server error:", err);
  process.exit(1);
});
SERVERJS

# Minimal production install - NO @sap/cds needed for the standalone server!
# Only install if there are actual npm dependencies (currently none needed)
echo "--- Production install in ${OUTPUT_DIR} ---"
cd "${OUTPUT_DIR}"
npm install --omit=dev --legacy-peer-deps --ignore-scripts || true

echo "=== Build complete. Files in ${OUTPUT_DIR}: ==="
ls -la "${OUTPUT_DIR}"
