export type MockResponse = {
  status: number
  body: unknown
}

export type MockRoute = {
  method: string
  url: string
  response: MockResponse
}

export function createMockApi(routes: MockRoute[]) {
  const byKey = new Map(routes.map((route) => [`${route.method.toUpperCase()} ${route.url}`, route.response] as const))

  return {
    async request(method: string, url: string) {
      const response = byKey.get(`${method.toUpperCase()} ${url}`)
      if (!response) {
        return { status: 404, body: { message: 'not found' } }
      }
      return response
    },
  }
}
