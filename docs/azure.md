# Azure Container Apps deployment configuration

infra/main.bicep is a parameterized, cost-conscious example for Azure Container Apps, ACR, Log Analytics, a managed identity, and an existing Azure SQL server. It does not provision anything automatically.

Prerequisites: Azure CLI, an existing subscription/resource group, ACR permissions, Azure SQL firewall/private networking, a Key Vault or Container Apps secret plan, and GitHub OIDC federated credentials. Expected billable resources include Container Apps environment/logging, ACR storage/builds, Azure SQL, and optional Key Vault.

Validate only:

    az bicep build --file infra/main.bicep
    az deployment group validate --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/parameters.dev.json

Deploy only with explicit authorization:

    az deployment group create --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/parameters.dev.json

Use separate parameter files for development, staging, and production. Roll back by redeploying the prior immutable image digest and only then applying backward-compatible database changes.
