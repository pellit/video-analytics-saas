/**
 * Billing API Service
 * Handles all subscription and billing related API calls
 */

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'

/**
 * Get authorization headers
 */
const getHeaders = (token) => ({
  'Content-Type': 'application/json',
  'Accept': 'application/json',
  'Authorization': `Bearer ${token}`
})

/**
 * Handle API response
 */
const handleResponse = async (response) => {
  const data = await response.json()
  if (!response.ok) {
    throw new Error(data.message || 'Error en la solicitud')
  }
  return data
}

/**
 * Get all available plans
 */
export const getPlans = async (token) => {
  const response = await fetch(`${API_URL}/billing/plans`, {
    headers: getHeaders(token)
  })
  return handleResponse(response)
}

/**
 * Get current user subscription
 */
export const getCurrentSubscription = async (token) => {
  const response = await fetch(`${API_URL}/billing/subscription`, {
    headers: getHeaders(token)
  })
  return handleResponse(response)
}

/**
 * Get current usage statistics
 */
export const getUsage = async (token) => {
  const response = await fetch(`${API_URL}/billing/usage`, {
    headers: getHeaders(token)
  })
  return handleResponse(response)
}

/**
 * Subscribe to a plan
 * @param {string} token - Auth token
 * @param {string} planSlug - Plan slug (free, pro, enterprise)
 * @param {string} billing - Billing cycle (monthly, annual)
 */
export const subscribeToPlan = async (token, planSlug, billing = 'monthly') => {
  const response = await fetch(`${API_URL}/billing/subscribe`, {
    method: 'POST',
    headers: getHeaders(token),
    body: JSON.stringify({
      plan: planSlug,
      billing_cycle: billing
    })
  })
  return handleResponse(response)
}

/**
 * Cancel current subscription
 */
export const cancelSubscription = async (token) => {
  const response = await fetch(`${API_URL}/billing/cancel`, {
    method: 'POST',
    headers: getHeaders(token)
  })
  return handleResponse(response)
}

/**
 * Resume a canceled subscription
 */
export const resumeSubscription = async (token) => {
  const response = await fetch(`${API_URL}/billing/resume`, {
    method: 'POST',
    headers: getHeaders(token)
  })
  return handleResponse(response)
}

/**
 * Change to a different plan
 * @param {string} token - Auth token
 * @param {string} planSlug - New plan slug
 */
export const changePlan = async (token, planSlug) => {
  const response = await fetch(`${API_URL}/billing/change-plan`, {
    method: 'POST',
    headers: getHeaders(token),
    body: JSON.stringify({ plan: planSlug })
  })
  return handleResponse(response)
}

/**
 * Get billing information (combined data)
 */
export const getBillingInfo = async (token) => {
  try {
    const [plans, subscription, usage] = await Promise.all([
      getPlans(token),
      getCurrentSubscription(token).catch(() => ({ subscription: null, plan: null })),
      getUsage(token).catch(() => ({ usage: {}, limits: {} }))
    ])

    return {
      plans: plans.plans || [],
      subscription: subscription.subscription,
      currentPlan: subscription.plan,
      usage: usage.usage || {},
      limits: usage.limits || {}
    }
  } catch (error) {
    console.error('Error fetching billing info:', error)
    throw error
  }
}

/**
 * Check if user can perform an action based on limits
 * @param {string} token - Auth token
 * @param {string} limitType - Type of limit to check (cameras, api_calls, analysis)
 * @param {number} count - Number to check against limit
 */
export const checkLimit = async (token, limitType, count = 1) => {
  const { limits, usage } = await getUsage(token)
  
  const limitMap = {
    cameras: { limitKey: 'max_cameras', usageKey: 'cameras' },
    api_calls: { limitKey: 'api_calls_per_day', usageKey: 'api_calls' },
    analysis: { limitKey: 'analysis_per_month', usageKey: 'analysis_count' }
  }

  const mapping = limitMap[limitType]
  if (!mapping) return { allowed: true }

  const limit = limits[mapping.limitKey]
  const current = usage[mapping.usageKey] || 0

  // -1 means unlimited
  if (limit === -1) return { allowed: true, unlimited: true }

  const allowed = (current + count) <= limit
  return {
    allowed,
    current,
    limit,
    remaining: Math.max(0, limit - current)
  }
}

export default {
  getPlans,
  getCurrentSubscription,
  getUsage,
  subscribeToPlan,
  cancelSubscription,
  resumeSubscription,
  changePlan,
  getBillingInfo,
  checkLimit
}
