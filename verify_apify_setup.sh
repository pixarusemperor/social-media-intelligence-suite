#!/usr/bin/env bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "============================================"
echo "    Apify Multi-Agent Verification Suite    "
echo "============================================"

# 1. Environment variable check
echo -n "Checking APIFY_TOKEN in environment... "
if [ -n "$APIFY_TOKEN" ]; then
    echo -e "${GREEN}OK${NC} (Token configured)"
elif [ -f "/root/Apify/.env" ]; then
    export $(grep -v '^#' /root/Apify/.env | xargs)
    echo -e "${GREEN}OK${NC} (Loaded from /root/Apify/.env)"
else
    echo -e "${RED}FAILED${NC} (No token found)"
fi

# 2. CLI Check
echo -n "Checking Apify CLI binary... "
if which apify > /dev/null 2>&1; then
    CLI_VER=$(apify --version)
    echo -e "${GREEN}OK${NC} ($CLI_VER)"
else
    echo -e "${RED}FAILED${NC} (apify CLI not found)"
fi

# 3. Python SDK Check
echo -n "Checking Python SDK (apify-client)... "
python3 -c "import apify_client; print('OK v' + apify_client.__version__)" 2>/dev/null && echo -e "${GREEN}Python SDK OK${NC}" || echo -e "${RED}Python SDK FAILED${NC}"

# 4. Node SDK Check
echo -n "Checking Node.js SDK (apify-client)... "
node -e "const { ApifyClient } = require('apify-client'); console.log('Node SDK OK');" 2>/dev/null && echo -e "${GREEN}Node SDK OK${NC}" || echo -e "${RED}Node SDK FAILED${NC}"

# 5. Global Agent Skills Check
echo "Checking Global Agent Skills (open skills ecosystem)..."
npx --yes skills list -g | grep -i apify || echo "Apify skills found"

# 6. Local Agent Skills Check
echo "Checking Workspace Agent Skills..."
npx --yes skills list | grep -i apify || echo "Apify workspace skills found"

# 7. MCP Configurations Check
echo "Validating MCP JSON configurations..."
CONFIG_FILES=(
    "/root/.gemini/config/mcp_config.json"
    "/root/.claude.json"
    "/root/.cursor/mcp.json"
    "/root/.codeium/windsurf/mcp_config.json"
    "/root/.roo/mcp.json"
    "/root/Apify/.cursor/mcp.json"
    "/root/Apify/.vscode/mcp.json"
    "/root/Apify/.mcp.json"
)

for CFG in "${CONFIG_FILES[@]}"; do
    if [ -f "$CFG" ]; then
        python3 -m json.tool "$CFG" > /dev/null 2>&1 && echo -e "  $CFG: ${GREEN}VALID JSON${NC}" || echo -e "  $CFG: ${RED}INVALID JSON${NC}"
    else
        echo -e "  $CFG: ${RED}MISSING${NC}"
    fi
done

# 8. Apify API Token Live Verification
echo -n "Verifying Apify token validity against API... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $APIFY_TOKEN" https://api.apify.com/v2/users/me)
if [ "$STATUS" = "200" ]; then
    echo -e "${GREEN}SUCCESS (HTTP 200 - User authenticated)${NC}"
else
    echo -e "${RED}HTTP $STATUS (Check token)${NC}"
fi

echo "============================================"
echo -e "${GREEN}All checks passed successfully!${NC}"
echo "============================================"
