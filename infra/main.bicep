param location string = resourceGroup().location
param appName string
param image string
param sqlServerFqdn string
param sqlDatabase string = 'HarvestOps'
param sqlAuthMode string = 'azure_identity'
param sqlUser string = ''
param acrName string
param keyVaultName string
param sqlPasswordSecretUri string = ''
param sessionRedisUrlSecretUri string
param secretKeySecretUri string
param entraClientSecretSecretUri string
param entraClientId string
param entraTenantId string
param entraRedirectUri string

resource logs 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${appName}-logs'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}
resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}
resource env 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: '${appName}-env'
  location: location
  properties: { appLogsConfiguration: { destination: 'log-analytics', logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey } } }
}
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${appName}-identity'
  location: location
}
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource keyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, identity.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-044c5c86b69e6')
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}
resource app 'Microsoft.App/containerApps@2023-05-01' = {
  name: appName
  location: location
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${identity.id}': {} } }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      ingress: { external: true, targetPort: 8050, transport: 'http' }
      registries: [{ server: acr.properties.loginServer, identity: identity.id }]
      secrets: concat(
        sqlAuthMode == 'sql_login' ? [
          { name: 'sql-password', keyVaultUrl: sqlPasswordSecretUri, identity: identity.id }
        ] : [],
        [
        { name: 'session-redis-url', keyVaultUrl: sessionRedisUrlSecretUri, identity: identity.id }
        { name: 'secret-key', keyVaultUrl: secretKeySecretUri, identity: identity.id }
        { name: 'entra-client-secret', keyVaultUrl: entraClientSecretSecretUri, identity: identity.id }
        ]
      )
    }
    template: {
      containers: [{
        name: 'harvestops'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: concat([
          { name: 'APP_ENV', value: 'production' }
          { name: 'DEMO_MODE', value: 'false' }
          { name: 'STORAGE_MODE', value: 'sqlserver' }
          { name: 'IDENTITY_MODE', value: 'entra' }
          { name: 'SQL_AUTH_MODE', value: sqlAuthMode }
          { name: 'SECRET_KEY', secretRef: 'secret-key' }
          { name: 'SQL_SERVER', value: sqlServerFqdn }
          { name: 'SQL_DATABASE', value: sqlDatabase }
          { name: 'SQL_USER', value: sqlUser }
          { name: 'SQL_ENCRYPT', value: 'true' }
          { name: 'SQL_TRUST_SERVER_CERTIFICATE', value: 'false' }
          { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
          { name: 'SESSION_REDIS_URL', secretRef: 'session-redis-url' }
          { name: 'ENTRA_CLIENT_ID', value: entraClientId }
          { name: 'ENTRA_TENANT_ID', value: entraTenantId }
          { name: 'ENTRA_REDIRECT_URI', value: entraRedirectUri }
          { name: 'ENTRA_CLIENT_SECRET', secretRef: 'entra-client-secret' }
        ], sqlAuthMode == 'sql_login' ? [
          { name: 'SQL_PASSWORD', secretRef: 'sql-password' }
        ] : [])
        probes: [{ type: 'Readiness', httpGet: { path: '/readyz', port: 8050 }, initialDelaySeconds: 15, periodSeconds: 20 }]
      }]
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}
output containerAppFqdn string = app.properties.configuration.ingress.fqdn
output acrLoginServer string = acr.properties.loginServer
