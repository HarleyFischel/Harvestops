# Azure Container Apps deployment configuration

infra/main.bicep is a parameterized, cost-conscious example for Azure Container Apps, ACR, Log Analytics, a managed identity, and an existing Azure SQL server. It does not provision anything automatically.

Prerequisites: Azure CLI, an existing subscription/resource group, ACR permissions, Azure SQL firewall/private networking, a Key Vault or Container Apps secret plan, and GitHub OIDC federated credentials. Expected billable resources include Container Apps environment/logging, ACR storage/builds, Azure SQL, and optional Key Vault.

The template expects an existing Key Vault and four secret URIs: SQL password, Redis session URL, the application secret key, and the Entra client secret. It grants the Container App user-assigned identity `Key Vault Secrets User` on that vault and `AcrPull` on the ACR. Create the SQL contained user separately and grant only the required database roles (`db_datareader`, `db_datawriter`, and `EXECUTE` on approved procedures). The template supplies the required production `IDENTITY_MODE=entra`, SQL login, Entra settings, verified SQL TLS settings, and Redis-backed session settings.

The release workflow is manual and requires environment-scoped variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `ACR_LOGIN_SERVER`, `RESOURCE_GROUP`, and `CONTAINER_APP_NAME`. With no `image_digest` input it logs into ACR through the federated Azure identity, pushes the AMD64 image with SHA/version tags, updates the app to the resulting immutable digest, and performs a `/healthz` smoke check. For staging-to-production promotion, pass the previously recorded `sha256:...` digest as `image_digest`; that path updates the app without rebuilding. GitHub environment approval rules must be configured in repository settings; YAML alone cannot create plan-dependent protections.

Validate only:

    az bicep build --file infra/main.bicep
    az deployment group validate --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/parameters.dev.json

Deploy only with explicit authorization:

    az deployment group create --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/parameters.dev.json

Use separate parameter files for development, staging, and production. Roll back by redeploying the prior immutable image digest and only then applying backward-compatible database changes.

Cleanup requires explicit authorization because it can delete billable resources and data. For a disposable resource group, review the resource list and then run:

    az resource list --resource-group "$RESOURCE_GROUP" --output table
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait

For shared resource groups, delete only the named Container App, managed environment, ACR, Log Analytics workspace, and user-assigned identity after confirming ownership. Do not delete an existing Azure SQL server or Key Vault unless its data-retention and recovery implications have been approved.
