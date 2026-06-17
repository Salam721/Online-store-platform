# Online Store UI — Design

## Tech Stack
- React 18 + TypeScript
- Vite (build tool)
- Tailwind CSS
- React Router v6
- No external state management library — React Context only

## Project Structure

```
ui/
├── .env.example           # VITE_API_URL=https://<api-id>.execute-api.us-east-1.amazonaws.com/prod
├── index.html
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json
├── src/
│   ├── main.tsx
│   ├── App.tsx            # Router setup, context providers
│   ├── api/
│   │   └── client.ts      # fetch wrapper — injects base URL and auth header
│   ├── contexts/
│   │   ├── AuthContext.tsx
│   │   └── CartContext.tsx
│   ├── components/
│   │   ├── ProductCard.tsx
│   │   ├── NavBar.tsx
│   │   └── ProtectedRoute.tsx
│   └── pages/
│       ├── Landing.tsx
│       ├── Catalog.tsx
│       ├── ProductDetail.tsx
│       ├── Cart.tsx
│       ├── Checkout.tsx
│       ├── OrderConfirmation.tsx
│       ├── Login.tsx
│       ├── Register.tsx
│       └── VerifyEmail.tsx
```

## Routing

| Path | Component | Protected |
|------|-----------|-----------|
| `/` | `Landing` | No |
| `/products` | `Catalog` | No |
| `/products/:id` | `ProductDetail` | No |
| `/cart` | `Cart` | No |
| `/checkout` | `Checkout` | Yes |
| `/orders/confirmation` | `OrderConfirmation` | Yes |
| `/login` | `Login` | No |
| `/register` | `Register` | No |
| `/verify-email` | `VerifyEmail` | No |

## Context Design

### AuthContext
```ts
interface AuthState {
  idToken: string | null
  accessToken: string | null
  sub: string | null        // decoded from idToken JWT claims
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}
```
- Tokens persisted in `localStorage` under keys `id_token`, `access_token`, `refresh_token`
- `sub` decoded client-side from idToken JWT payload (base64 decode middle segment — no library needed)
- On mount, reads tokens from localStorage to restore session

### CartContext
```ts
interface CartItem {
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
```
- Persisted in `localStorage` under key `cart`

## API Client

`src/api/client.ts` — thin wrapper around `fetch`:
- Base URL from `import.meta.env.VITE_API_URL`
- Attaches `Authorization: Bearer <idToken>` when token is present in localStorage
- Throws on non-2xx responses with the error message from the response body

## Data Shapes (from backend)

```ts
interface Product {
  id: string
  title: string
  category: string
  description: string
  price: number
  image_url?: string
}

interface OrderPayload {
  customer_id: string       // Cognito sub
  items: { productId: string; title: string; price: number; quantity: number }[]
  total_amount: number
  shipping_address: {
    street: string; city: string; state: string; zip: string; country: string
  }
  payment_method: string    // free text, no processing
}

interface OrderResponse {
  order_id: string
  status: 'accepted'
  message: string
}
```

## Key Component Behaviours

**ProductCard** — displays title, category, price, image (or grey placeholder). Clicking navigates to `/products/:id`.

**Catalog** — fetches `GET /products` on mount. Category buttons derived from unique categories in the response. Search filters client-side on `title`. Both filters compose (category AND search term).

**Checkout** — reads cart from CartContext, reads `sub` from AuthContext for `customer_id`. On 202, passes `order_id` via router state to `OrderConfirmation` and calls `clearCart()`.

**ProtectedRoute** — wraps React Router `<Outlet>`. If `!isAuthenticated`, redirects to `/login` with `state.from` set so login can redirect back.

**VerifyEmail** — static page shown after register. No API call. Tells user to check their email.
