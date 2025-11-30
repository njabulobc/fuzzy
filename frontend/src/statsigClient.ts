import { StatsigClient, StatsigOptions, StatsigUser } from 'statsig-js'

const clientKey = (import.meta.env.VITE_STATSIG_CLIENT_KEY as string | undefined) || ''
const environmentTier =
  (import.meta.env.VITE_STATSIG_ENVIRONMENT as string | undefined) || 'development'

let client: StatsigClient | null = null
let initializePromise: Promise<void> | null = null

function ensureClient(user?: StatsigUser): StatsigClient | null {
  if (!clientKey) return null

  if (!client) {
    const options: StatsigOptions = {
      environment: { tier: environmentTier }
    }
    client = new StatsigClient(clientKey, user ?? { userID: 'anonymous' }, options)
    initializePromise = client.initializeAsync()
  } else if (user) {
    initializePromise = (async () => {
      if (initializePromise) {
        await initializePromise
      }
      await client!.updateUser(user)
    })()
  }

  return client
}

export async function initMonitoring(user?: StatsigUser): Promise<void> {
  const statsigClient = ensureClient(user)
  if (!statsigClient || !initializePromise) return
  await initializePromise
}

export async function logEvent(
  eventName: string,
  value?: string | number | null,
  metadata?: Record<string, unknown>
): Promise<void> {
  const statsigClient = ensureClient()
  if (!statsigClient || !initializePromise) return

  await initializePromise
  statsigClient.logEvent(eventName, value ?? null, metadata)
}

export function shutdownMonitoring(): void {
  client?.shutdown()
}

export function isMonitoringEnabled(): boolean {
  return Boolean(clientKey)
}
