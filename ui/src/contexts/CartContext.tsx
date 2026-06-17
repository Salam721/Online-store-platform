import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import type { Product } from '@/components/ProductCard'

export interface CartItem {
  productId: string
  title: string
  price: number
  quantity: number
  imageUrl?: string
}

interface CartState {
  items: CartItem[]
  addItem: (product: Product, quantity: number) => void
  removeItem: (productId: string) => void
  updateQuantity: (productId: string, quantity: number) => void
  clearCart: () => void
  total: number
}

const CartContext = createContext<CartState | null>(null)

function loadCart(): CartItem[] {
  try {
    return JSON.parse(localStorage.getItem('cart') ?? '[]')
  } catch {
    return []
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<CartItem[]>(loadCart)

  useEffect(() => {
    localStorage.setItem('cart', JSON.stringify(items))
  }, [items])

  function addItem(product: Product, quantity: number) {
    setItems(prev => {
      const existing = prev.find(i => i.productId === product.id)
      if (existing) {
        return prev.map(i => i.productId === product.id ? { ...i, quantity: i.quantity + quantity } : i)
      }
      return [...prev, { productId: product.id, title: product.title, price: product.price, quantity, imageUrl: product.image_url }]
    })
  }

  function removeItem(productId: string) {
    setItems(prev => prev.filter(i => i.productId !== productId))
  }

  function updateQuantity(productId: string, quantity: number) {
    setItems(prev => prev.map(i => i.productId === productId ? { ...i, quantity } : i))
  }

  function clearCart() {
    setItems([])
  }

  const total = items.reduce((sum, i) => sum + i.price * i.quantity, 0)

  return (
    <CartContext.Provider value={{ items, addItem, removeItem, updateQuantity, clearCart, total }}>
      {children}
    </CartContext.Provider>
  )
}

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within CartProvider')
  return ctx
}
