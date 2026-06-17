import type { Product } from '@/components/ProductCard'

const BASE_URL = import.meta.env.VITE_API_URL as string

function authHeader(): Record<string, string> {
  const token = localStorage.getItem('id_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeader(), ...init.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw Object.assign(new Error(body.message ?? res.statusText), { status: res.status })
  }
  return res.json()
}

export interface LoginResponse {
  idToken: string
  accessToken: string
  refreshToken: string
}

export interface OrderPayload {
  customer_id: string
  items: { productId: string; title: string; price: number; quantity: number }[]
  total_amount: number
  shipping_address: { street: string; city: string; state: string; zip: string; country: string }
  payment_method: string
}

export interface OrderResponse {
  order_id: string
  status: string
  message: string
}

export const getProducts = (category?: string) =>
  request<Product[]>(`/products${category ? `?category=${encodeURIComponent(category)}` : ''}`)

export const getProduct = (id: string) => request<Product>(`/products/${id}`)

export const login = (email: string, password: string) =>
  request<LoginResponse>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })

export const register = (email: string, password: string, name: string) =>
  request<void>('/auth/register', { method: 'POST', body: JSON.stringify({ email, password, name }) })

export const placeOrder = (payload: OrderPayload) =>
  request<OrderResponse>('/orders', { method: 'POST', body: JSON.stringify(payload) })
