import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { useApiData } from './useApiData'
import { Section } from './components/ui'

// Tiny probe component to drive the hook.
function Probe({ fn }) {
  const { data, loading, error } = useApiData(fn)
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="error">{error ?? ''}</span>
      <span data-testid="data">{data ? JSON.stringify(data) : ''}</span>
    </div>
  )
}

describe('useApiData', () => {
  beforeEach(() => vi.stubGlobal('fetch', vi.fn()))

  it('loads data on success', async () => {
    fetch.mockResolvedValueOnce({ ok: true, status: 200, json: async () => ({ n: 8 }) })
    render(<Probe fn={() => fetch('/x').then((r) => r.json())} />)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('data').textContent).toBe('{"n":8}')
    expect(screen.getByTestId('error').textContent).toBe('')
  })

  it('captures error without throwing on failure', async () => {
    fetch.mockRejectedValueOnce(new TypeError('nope'))
    render(<Probe fn={() => fetch('/x').then((r) => r.json())} />)
    await waitFor(() => expect(screen.getByTestId('loading').textContent).toBe('false'))
    expect(screen.getByTestId('error').textContent).not.toBe('')
  })
})

describe('Section partial-failure isolation', () => {
  it('renders an error state with retry, not a crash', () => {
    render(
      <Section title="X" error="boom" onRetry={() => {}}>
        <p>hidden</p>
      </Section>,
    )
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.getByRole('button', { name: /try again/i })).toBeTruthy()
    expect(screen.queryByText('hidden')).toBeNull()
  })

  it('renders loading state', () => {
    render(<Section title="X" loading><p>hidden</p></Section>)
    expect(screen.getByRole('status')).toBeTruthy()
  })

  it('renders children when healthy', () => {
    render(<Section title="X"><p>visible-body</p></Section>)
    expect(screen.getByText('visible-body')).toBeTruthy()
  })
})
