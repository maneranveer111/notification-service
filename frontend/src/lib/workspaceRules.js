export function canDeleteWorkspace(workspace, role) {
  if (!workspace || typeof workspace !== 'object') return false;
  if (role !== 'owner') return false;
  return workspace.deletable === true;
}
