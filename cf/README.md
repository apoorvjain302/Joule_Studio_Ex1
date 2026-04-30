# Cloud Foundry Deployment Guide
## EWM Pallet Verification Solution

---

## ⚠️ Important: What Changes on Cloud Foundry

This solution was built for **SAP App Foundation**, which provides managed MCP servers and an Agent Gateway (AGW). On Cloud Foundry, two things work differently:

### 1. MCP Servers → Direct EWM API calls
The `ewm-outbound-delivery-mcp-server` and `ewm-handling-unit-mcp-server` assets have
**no source code** — they are fully managed by App Foundation. On CF, the agent must
call the EWM OData APIs directly using `EWM_BASE_URL`, `EWM_USERNAME`, and `EWM_PASSWORD`
environment variables (set in manifest.yml).

The `mcp_client.py` in the agent connects to App Foundation's Agent Gateway (AGW) —
this connection will silently return no tools on CF (it gracefully degrades). The agent
will fall back to direct HTTP tool calls.

### 2. SAP Cloud SDK
The `sap-cloud-sdk` package in `requirements.txt` is installed from a private SAP
Artifactory registry. You must either:
- Replace it with the public PyPI version: `sap-cloud-sdk`
- Or host the wheel file in your own registry

---

## Prerequisites

| Requirement | How to set up |
|-------------|--------------|
| CF CLI installed | `brew install cloudfoundry/tap/cf-cli@8` |
| Docker installed | For building images |
| Container registry | Docker Hub, SAP BTP Container Registry, or any OCI registry |
| SAP AI Core | Service instance in your BTP subaccount (plan: `extended`) |
| S/4HANA / EWM access | Service user with OData API permissions |

---

## Step 1 — Fix the SDK Dependency

Edit `assets/pallet-verification-agent/requirements.txt` and replace the private SDK line:

```diff
- sap-cloud-sdk @ https://common.repositories.cloud.sap/artifactory/...
+ sap-cloud-sdk
```

---

## Step 2 — Build and Push the Agent Docker Image

```bash
cd assets/pallet-verification-agent

docker build -t <your-registry>/pallet-verification-agent:latest .
docker push <your-registry>/pallet-verification-agent:latest

cd ../..
```

> Replace `<your-registry>` with your Docker Hub username or registry URL
> e.g. `mydockerhub/pallet-verification-agent:latest`

---

## Step 3 — Install UI Dependencies

```bash
cd assets/pallet-verification-ui
npm install
cd ../..
```

---

## Step 4 — Update manifest.yml

Open `cf/manifest.yml` and replace all placeholders:

| Placeholder | Replace with |
|-------------|-------------|
| `<your-registry>` | Your Docker registry (e.g. `mydockerhub`) |
| `<your-cf-domain>` | Your CF apps domain (e.g. `cfapps.eu10.hana.ondemand.com`) |
| `<your-openai-api-key>` | OpenAI API key **or** AI Core credentials |
| `<your-s4hana-host>` | Your S/4HANA system hostname |
| `<ewm-service-user>` | EWM OData service user |
| `<ewm-service-password>` | EWM OData service user password |
| `<your-warehouse-id>` | Your EWM warehouse number |

---

## Step 5 — Log in to Cloud Foundry

```bash
cf login -a https://api.cf.<region>.hana.ondemand.com
# Enter your BTP credentials when prompted
# Select your org and space
```

---

## Step 6 — Deploy

```bash
# Deploy both apps from the project root
cf push --manifest cf/manifest.yml
```

Or deploy individually:

```bash
# Agent only
cf push pallet-verification-agent --manifest cf/manifest.yml

# UI only
cf push pallet-verification-ui --manifest cf/manifest.yml
```

---

## Step 7 — Update AGENT_PUBLIC_URL

After the first deploy, get the assigned agent URL:

```bash
cf app pallet-verification-agent | grep routes
# e.g. routes: pallet-verification-agent.cfapps.eu10.hana.ondemand.com
```

Update the env var and restage:

```bash
cf set-env pallet-verification-agent AGENT_PUBLIC_URL https://pallet-verification-agent.cfapps.eu10.hana.ondemand.com
cf restage pallet-verification-agent
```

---

## Step 8 — Verify Deployment

```bash
# Check agent is running
curl https://pallet-verification-agent.<your-cf-domain>/.well-known/agent.json

# Check UI is running
open https://pallet-verification-ui.<your-cf-domain>
```

---

## Useful CF Commands

```bash
# View logs
cf logs pallet-verification-agent --recent
cf logs pallet-verification-ui --recent

# Live logs
cf logs pallet-verification-agent

# Restart an app
cf restart pallet-verification-agent

# Check app status
cf app pallet-verification-agent

# Set an environment variable
cf set-env pallet-verification-agent EWM_WAREHOUSE_ID 1710
cf restage pallet-verification-agent

# Scale instances
cf scale pallet-verification-agent -i 2
```

---

## Using SAP AI Core Instead of OpenAI (Recommended)

If you have SAP AI Core in your BTP account:

1. Create a service instance:
   ```bash
   cf create-service aicore extended pallet-verification-aicore
   ```

2. Create a service key:
   ```bash
   cf create-service-key pallet-verification-aicore mykey
   cf service-key pallet-verification-aicore mykey
   ```

3. Extract credentials and set env vars:
   ```bash
   cf set-env pallet-verification-agent AICORE_AUTH_URL <auth_url>
   cf set-env pallet-verification-agent AICORE_CLIENT_ID <client_id>
   cf set-env pallet-verification-agent AICORE_CLIENT_SECRET <client_secret>
   cf set-env pallet-verification-agent AICORE_BASE_URL <api_url>
   cf set-env pallet-verification-agent AICORE_RESOURCE_GROUP default
   cf restage pallet-verification-agent
   ```

4. In `manifest.yml`, comment out `OPENAI_API_KEY` and uncomment the AI Core block.
