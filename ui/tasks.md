# Online Store UI — Tasks

## 1. Project Setup
- [ ] Scaffold Vite + React + TypeScript project in `ui/`
- [ ] Install and configure Tailwind CSS
- [ ] Install React Router v6
- [ ] Create `.env.example` with `VITE_API_URL` placeholder
- [ ] Set up `tsconfig.json` with strict mode and path aliases

## 2. API Client
- [ ] Create `src/api/client.ts` — fetch wrapper with base URL injection and auth header
- [ ] Export typed functions: `getProducts(category?)`, `getProduct(id)`, `login(email, password)`, `register(email, password, name)`, `placeOrder(payload)`

## 3. AuthContext
- [ ] Create `src/contexts/AuthContext.tsx`
- [ ] Implement token storage in localStorage
- [ ] Implement `sub` extraction from idToken JWT payload
- [ ] Implement `login()`, `logout()`, session restore on mount
- [ ] Wrap app in `AuthProvider` in `App.tsx`

## 4. CartContext
- [ ] Create `src/contexts/CartContext.tsx`
- [ ] Implement `addItem`, `removeItem`, `updateQuantity`, `clearCart`
- [ ] Persist cart to localStorage
- [ ] Compute `total` as derived value
- [ ] Wrap app in `CartProvider` in `App.tsx`

## 5. Routing & ProtectedRoute
- [ ] Set up all routes in `App.tsx` using React Router v6
- [ ] Create `src/components/ProtectedRoute.tsx` — redirect to `/login` if unauthenticated, preserve `from` in router state

## 6. NavBar
- [ ] Create `src/components/NavBar.tsx`
- [ ] Show logo/home link, catalog link, cart icon with item count badge
- [ ] Show login/register or logout based on auth state
- [ ] Mobile: hamburger menu

## 7. Pages

### Landing
- [ ] Hero section with CTA linking to `/products`
- [ ] Static — no API calls

### Catalog
- [ ] Fetch `GET /products` on mount, show loading spinner
- [ ] Render category filter buttons (derived from response)
- [ ] Render search input (client-side filter on title)
- [ ] Render `ProductCard` grid
- [ ] Handle empty state and error state

### ProductCard component
- [ ] Create `src/components/ProductCard.tsx`
- [ ] Display image (with grey placeholder fallback), title, category, price
- [ ] Navigate to `/products/:id` on click

### Product Detail
- [ ] Fetch `GET /products/:id` on mount
- [ ] Display all product fields
- [ ] Quantity selector (min 1)
- [ ] Add to cart button → calls `CartContext.addItem`
- [ ] Handle loading, not found, and error states

### Cart
- [ ] List cart items with title, quantity controls, unit price, line total
- [ ] Remove item button
- [ ] Order total
- [ ] Empty cart message
- [ ] Checkout button → navigates to `/checkout`

### Login
- [ ] Email + password form
- [ ] Calls `AuthContext.login()`
- [ ] On success, redirect to `from` or `/products`
- [ ] Show error message on 401
- [ ] Link to `/register`

### Register
- [ ] Name + email + password form
- [ ] Calls `register()` from API client
- [ ] On success (201), redirect to `/verify-email`
- [ ] Show error on 409 (email taken) and validation errors

### Verify Email
- [ ] Static confirmation screen
- [ ] Message: check email to verify account before logging in
- [ ] Link to `/login`

### Checkout
- [ ] Protected route
- [ ] Order summary from CartContext
- [ ] Shipping address form (street, city, state, zip, country)
- [ ] Payment method input (free text)
- [ ] Submit calls `placeOrder()` with `customer_id` from `AuthContext.sub`
- [ ] On 202, navigate to `/orders/confirmation` passing `order_id` via router state
- [ ] Disable submit while loading

### Order Confirmation
- [ ] Protected route
- [ ] Read `order_id` from router state
- [ ] Call `CartContext.clearCart()` on mount
- [ ] Display order ID and success message
- [ ] Link back to `/products`

## 8. Responsive Polish
- [ ] Verify all pages at 375px, 768px, 1280px
- [ ] Catalog grid: 1 col mobile, 2 col tablet, 3–4 col desktop
- [ ] NavBar collapses to hamburger on mobile

## 9. Error & Loading States
- [ ] Global: 401 response clears auth and redirects to login
- [ ] All data-fetching pages show spinner while loading
- [ ] All data-fetching pages show error message on failure

## 10. Environment & Build
- [ ] Confirm `VITE_API_URL` is the only required env variable
- [ ] Add `ui/README.md` with setup instructions (`npm install`, `cp .env.example .env`, `npm run dev`)
- [ ] Verify production build (`npm run build`) has no TypeScript errors
