param location string = resourceGroup().location
param appName string
param image string
param sqlServerFqdn string
param sqlDatabase string = 'HarvestOps'
param acrName string
param sqlPasswordSecretUri string
param sessionRedisUrlSecretUri string

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
resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
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
      secrets: [
        { name: 'sql-password', keyVaultUrl: sqlPasswordSecretUri, identity: identity.id }
        { name: 'session-redis-url', keyVaultUrl: sessionRedisUrlSecretUri, identity: identity.id }
      ]
    }
    template: {
      containers: [{
        name: 'harvestops'
        image: image
        resources: { cpu: json('0.5'), memory: '1Gi' }
        env: [
          { name: 'APP_ENV', value: 'production' }
          { name: 'DEMO_MODE', value: 'false' }
          { name: 'STORAGE_MODE', value: 'sqlserver' }
          { name: 'SQL_SERVER', value: sqlServerFqdn }
          { name: 'SQL_DATABASE', value: sqlDatabase }
          { name: 'SQL_ENCRYPT', value: 'true' }
          { name: 'SQL_TRUST_SERVER_CERTIFICATE', value: 'false' }
          { name: 'SQL_PASSWORD', secretRef: 'sql-password' }
          { name: 'SESSION_REDIS_URL', secretRef: 'session-redis-url' }
        ]
        probes: [{ type: 'Readiness', httpGet: { path: '/readyz', port: 8050 }, initialDelaySeconds: 15, periodSeconds: 20 }]
      }]
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}
output containerAppFqdn string = app.properties.configuration.ingress.fqdn
output acrLoginServer string = acr.properties.loginServer
