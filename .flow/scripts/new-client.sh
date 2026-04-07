#!/bin/bash
# Usage: bash .flow/scripts/new-client.sh <client-id> "<Client Display Name>"
# Example: bash .flow/scripts/new-client.sh acme-corp "Acme Corp"

CLIENT_ID=$1
CLIENT_NAME=$2

if [ -z "$CLIENT_ID" ] || [ -z "$CLIENT_NAME" ]; then
  echo "Usage: bash .flow/scripts/new-client.sh <client-id> \"<Client Display Name>\""
  exit 1
fi

echo "Setting up client: $CLIENT_NAME ($CLIENT_ID)"

# Create directories
mkdir -p clients/$CLIENT_ID/.agents
mkdir -p clients/$CLIENT_ID/product/requirements
mkdir -p clients/$CLIENT_ID/product/knowledge/faqs
mkdir -p clients/$CLIENT_ID/product/knowledge/services
mkdir -p clients/$CLIENT_ID/product/knowledge/policies
mkdir -p clients/$CLIENT_ID/product/flows
mkdir -p clients/$CLIENT_ID/product/prompts

echo "  ✅ Directories created"

# Copy and populate agent templates
declare -A TEMPLATES=(
  ["orchestrator"]=".flow/templates/client-orchestrator.md"
  ["pm-agent"]=".flow/templates/client-pm-agent.md"
  ["engineering-agent"]=".flow/templates/client-engineering-agent.md"
  ["qa-agent"]=".flow/templates/client-qa-agent.md"
  ["prompt-persona-agent"]=".flow/templates/client-prompt-persona-agent.md"
  ["knowledge-agent"]=".flow/templates/client-knowledge-agent.md"
)

for AGENT in "${!TEMPLATES[@]}"; do
  SRC="${TEMPLATES[$AGENT]}"
  sed "s/\[CLIENT NAME\]/$CLIENT_NAME/g" $SRC > clients/$CLIENT_ID/.agents/$AGENT.md
  echo "  ✅ Created .agents/$AGENT.md"
done

# Create context file
cat > clients/$CLIENT_ID/context.md << EOF
# $CLIENT_NAME — Client Context

## Business
- Industry: [TO FILL]
- Primary users: [TO FILL]
- Internal users: [TO FILL]

## AI Agent Purpose
- [TO FILL]

## Key Constraints
- [TO FILL]

## Integration Points
- [TO FILL]

## Product Documents
- PRD: product/PRD.md
- Changelog: product/changelog.md
- Persona: product/persona.md
- Knowledge Base: product/knowledge/
EOF

# Create empty product files
touch clients/$CLIENT_ID/product/PRD.md
touch clients/$CLIENT_ID/product/changelog.md
touch clients/$CLIENT_ID/product/persona.md
touch clients/$CLIENT_ID/product/knowledge/pricing.md
touch clients/$CLIENT_ID/product/knowledge/hours.md

echo "  ✅ Product files created"
echo ""
echo "✅ Client '$CLIENT_NAME' set up at clients/$CLIENT_ID"
echo ""
echo "👉 Next steps:"
echo "   1. Fill in clients/$CLIENT_ID/context.md"
echo "   2. Add client-specific rules to clients/$CLIENT_ID/.agents/pm-agent.md"
echo "   3. Add brand voice to clients/$CLIENT_ID/.agents/prompt-persona-agent.md"
echo "   4. Add knowledge sources to clients/$CLIENT_ID/.agents/knowledge-agent.md"
echo "   5. Add $CLIENT_ID to .flow/config.yaml under clients:"
echo ""
echo "      $CLIENT_ID:"
echo "        path: clients/$CLIENT_ID"
echo "        agents: clients/$CLIENT_ID/.agents"
echo "        context: clients/$CLIENT_ID/context.md"
echo "        product: clients/$CLIENT_ID/product"
echo "        knowledge_base: clients/$CLIENT_ID/product/knowledge"
echo "        prompt_library: clients/$CLIENT_ID/product/prompts"
echo "        persona: clients/$CLIENT_ID/product/persona.md"
