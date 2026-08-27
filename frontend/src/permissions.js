const ADMIN_ROLES = new Set(['admin', 'super_admin'])

export const can = (profile, permission) => ADMIN_ROLES.has(profile?.role)
  || (Array.isArray(profile?.permissions) && profile.permissions.includes(permission))
