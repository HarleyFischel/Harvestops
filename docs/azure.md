# Azure Container Apps deployment configuration

infra/main.bicep is a parameterized, cost-conscious example for Azure Container Apps, ACR, Log Analytics, a managed identity, and an existing Azure SQL server. It does not provision anything automatically.

Prerequisites: Azure CLI, an existing subscription/resource group, ACR permissions, Azure SQL firewall/private networking, an existing Azure Cache for Redis or compatible managed Redis endpoint, a Key Vault or Container Apps secret plan, and GitHub OIDC federated credentials. Expected billable resources include Container Apps environment/logging, ACR storage/builds, Azure SQL, the shared Redis service, and optional Key Vault.

The template expects an existing Key Vault for the shared Redis session URL, application secret key, and Entra client secret. Store a TLS-protected `rediss://` connection URI for the managed Redis service as the `harvestops-session-redis-url` secret and pass its versioned URI as `sessionRedisUrlSecretUri`. The Container App receives it as `SESSION_REDIS_URL`; Flask-Session then stores session state outside the replica filesystem so multiple workers and replicas share authentication state. No container-local session files or durable application state are supported in production. The template grants the Container App user-assigned identity `Key Vault Secrets User` on that vault and `AcrPull` on the ACR. Staging and production parameter files select `sqlAuthMode=azure_identity`, so the application requests an Azure SQL access token through `DefaultAzureCredential` rather than storing a SQL password. Create a contained Azure SQL user for the managed identity separately and grant only the required database roles (`db_datareader`, `db_datawriter`, and `EXECUTE` on approved procedures). The development parameter file retains `sqlAuthMode=sql_login` for a configured nonproduction SQL login. The template supplies the required production `IDENTITY_MODE=entra`, verified SQL TLS settings, and Redis-backed session settings.

After the managed identity exists and an Entra administrator is configured for the Azure SQL logical server, apply the least-privilege database grant in the target database. Replace the bracketed identity name with the user-assigned identity display name from the deployment:

```sql
CREATE USER [harvestops-prod-identity] FROM EXTERNAL PROVIDER;
ALTER ROLE db_datareader ADD MEMBER [harvestops-prod-identity];
ALTER ROLE db_datawriter ADD MEMBER [harvestops-prod-identity];
GRANT EXECUTE ON SCHEMA::dbo TO [harvestops-prod-identity];
```

This SQL grant, Entra administrator setup, and token-authenticated Azure SQL connection remain deployment prerequisites and are not verified locally.

The ADF examples are `adf/pipeline-shipment-import.json` and `adf/trigger-shipment-import.json`. The trigger is an unverified UTC hourly example; deploy it only after configuring linked services, datasets, source paths, and the target Azure SQL connection.

The Bicep template also creates a manual Container Apps Job named `${appName}-migrate` by default. It runs the same immutable image with `python db/run_migrations.py`, uses the same managed identity and Key Vault references, and is deliberately not started as part of web-app rollout. Start it only after reviewing the migration and image digest:

    az containerapp job start --name "${APP_NAME}-migrate" --resource-group "$RESOURCE_GROUP"
    az containerapp job execution list --name "${APP_NAME}-migrate" --resource-group "$RESOURCE_GROUP" --output table

Set `enableMigrationJob` to `false` only when an approved external migration runner is used. The job resource is configuration-only until Azure credentials and a target environment are supplied; it was not deployed or executed in this validation.

The release workflow is manual and requires environment-scoped variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `ACR_NAME`, `ACR_LOGIN_SERVER`, `RESOURCE_GROUP`, and `CONTAINER_APP_NAME`. With no `image_digest` input it logs into ACR through the federated Azure identity, pushes the AMD64 image with SHA/version tags, updates the app to the resulting immutable digest, and performs a `/healthz` smoke check. For staging-to-production promotion, pass the previously recorded `sha256:...` digest as `image_digest`; that path updates the app without rebuilding. GitHub environment approval rules must be configured in repository settings; YAML alone cannot create plan-dependent protections.

Validate only:

    az bicep build --file infra/main.bicep
    az deployment group validate --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/parameters.dev.json

Deploy only with explicit authorization:

    az deployment group create --resource-group "$RESOURCE_GROUP" --template-file infra/main.bicep --parameters @infra/parameters.dev.json

Use `infra/parameters.dev.json`, `infra/parameters.staging.json`, and `infra/parameters.prod.json` as separate environment templates. Replace every documented placeholder through deployment-time configuration; do not commit secret values. Roll back by redeploying the prior immutable image digest and only then applying backward-compatible database changes.

Cleanup requires explicit authorization because it can delete billable resources and data. For a disposable resource group, review the resource list and then run:

    az resource list --resource-group "$RESOURCE_GROUP" --output table
    az group delete --name "$RESOURCE_GROUP" --yes --no-wait

For shared resource groups, delete only the named Container App, managed environment, ACR, Log Analytics workspace, and user-assigned identity after confirming ownership. Do not delete an existing Azure SQL server or Key Vault unless its data-retention and recovery implications have been approved.
