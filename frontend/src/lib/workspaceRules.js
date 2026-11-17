export function canDeleteWorkspace(workspace, role) {
  if (!workspace || typeof workspace !== 'object') return false;
  if (role !== 'owner') return false;
  if (workspace.slug === 'default') return false;
  return true;
}
