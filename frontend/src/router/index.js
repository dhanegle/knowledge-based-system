import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { guest: true },
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('../views/RegisterView.vue'),
    meta: { guest: true },
  },
  {
    path: '/',
    component: () => import('../views/AppLayout.vue'),
    meta: { auth: true },
    children: [
      { path: '', name: 'chat', component: () => import('../views/ChatView.vue') },
      { path: 'documents', name: 'documents', component: () => import('../views/DocumentsView.vue') },
      { path: 'users', name: 'users', component: () => import('../views/UsersView.vue'), meta: { admin: true } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.auth && !auth.isLoggedIn) {
    return { name: 'login' }
  }
  if (to.meta.guest && auth.isLoggedIn) {
    return { name: 'chat' }
  }
  if (to.meta.admin && !auth.isAdmin) {
    return { name: 'chat' }
  }
})

export default router
