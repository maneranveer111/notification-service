import { useState, useEffect, useCallback } from 'react';
import {
  LayoutTemplate,
  Plus,
  X,
} from 'lucide-react';
import {
  listTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
} from '../lib/api';
import { useAuth } from '../lib/auth';
import Pagination from '../components/Pagination';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';
import Button from '../components/ui/Button';
import Input from '../components/ui/Input';
import Select from '../components/ui/Select';
import Badge from '../components/ui/Badge';

function extractVariables(body = '', subject = '') {
  const combined = `${subject} ${body}`;
  const regex = /\{\{\s*(\w+)\s*\}\}/g;
  const set = new Set();
  let m;
  while ((m = regex.exec(combined)) !== null) {
    set.add(m[1]);
  }
  return Array.from(set);
}

export default function TemplatesPage() {
  const { canWrite } = useAuth();

  const [templates, setTemplates] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Modals
  const [modalMode, setModalMode] = useState(null); // 'create' | 'edit' | 'view' | null
  const [activeTemplate, setActiveTemplate] = useState(null);

  // Form State
  const [formName, setFormName] = useState('');
  const [formChannel, setFormChannel] = useState('email');
  const [formSubject, setFormSubject] = useState('');
  const [formBody, setFormBody] = useState('');
  const [formError, setFormError] = useState(null);
  const [saving, setSaving] = useState(false);

  // Delete Dialog
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchTemplates = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listTemplates({
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      setTemplates(res.data || []);
      setTotal(res.total || 0);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    fetchTemplates();
  }, [fetchTemplates]);

  function openCreate() {
    setActiveTemplate(null);
    setFormName('');
    setFormChannel('email');
    setFormSubject('');
    setFormBody('');
    setFormError(null);
    setModalMode('create');
  }

  function openEdit(tpl) {
    setActiveTemplate(tpl);
    setFormName(tpl.name || '');
    setFormChannel(tpl.channel || 'email');
    setFormSubject(tpl.subject_template || '');
    setFormBody(tpl.body_template || '');
    setFormError(null);
    setModalMode('edit');
  }

  function openView(tpl) {
    setActiveTemplate(tpl);
    setFormName(tpl.name || '');
    setFormChannel(tpl.channel || 'email');
    setFormSubject(tpl.subject_template || '');
    setFormBody(tpl.body_template || '');
    setFormError(null);
    setModalMode('view');
  }

  function closeModal() {
    setModalMode(null);
    setActiveTemplate(null);
    setFormError(null);
  }

  const detectedVars = extractVariables(
    formBody,
    formChannel === 'email' ? formSubject : ''
  );

  async function handleSave(e) {
    e.preventDefault();
    if (modalMode === 'view') return;

    if (!formName.trim()) {
      setFormError('Template name is required.');
      return;
    }
    if (!formBody.trim()) {
      setFormError('Body template is required.');
      return;
    }
    if (formBody.length > 10000) {
      setFormError('Body cannot exceed 10000 characters.');
      return;
    }

    setSaving(true);
    setFormError(null);

    try {
      const payload = {
        name: formName.trim(),
        channel: formChannel,
        body_template: formBody,
        subject_template:
          formChannel === 'email' ? formSubject.trim() || null : null,
      };

      if (modalMode === 'create') {
        await createTemplate(payload);
      } else if (modalMode === 'edit') {
        await updateTemplate(activeTemplate.id, payload);
      }

      closeModal();
      fetchTemplates();
    } catch (err) {
      setFormError(err.message || String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeleteConfirm() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await deleteTemplate(deleteTarget.id);
      setDeleteTarget(null);
      fetchTemplates();
    } catch (err) {
      setError(err);
      setDeleteTarget(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-semibold text-[#1C1917] tracking-tight">
            Templates
          </h1>
          <p className="text-xs sm:text-sm text-[#78716C] mt-0.5">
            Reusable message content with Jinja2 and variable interpolation.
          </p>
        </div>
        {canWrite && (
          <Button
            variant="primary"
            size="sm"
            onClick={openCreate}
            icon={Plus}
          >
            New Template
          </Button>
        )}
      </div>

      {error && <ErrorBanner error={error} onRetry={fetchTemplates} />}

      {loading && templates.length === 0 ? (
        <Loading text="Loading templates…" />
      ) : templates.length === 0 ? (
        <EmptyState
          icon={LayoutTemplate}
          title="No templates"
          message="Create your first message template with dynamic variables."
          action={
            canWrite && (
              <Button
                variant="primary"
                size="sm"
                onClick={openCreate}
                icon={Plus}
              >
                Create Template
              </Button>
            )
          }
        />
      ) : (
        <div className="bg-white border border-[#E7E5E4] rounded-[8px] overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs min-w-[700px]">
              <thead className="bg-[#FAFAF9] border-b border-[#E7E5E4] text-[11px] font-semibold text-[#78716C] uppercase tracking-wider">
                <tr>
                  <th className="px-5 py-3">Name</th>
                  <th className="px-5 py-3">Channel</th>
                  <th className="px-5 py-3">Variables</th>
                  <th className="px-5 py-3">Updated</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E7E5E4]">
                {templates.map((tpl) => (
                  <tr
                    key={tpl.id}
                    className="hover:bg-[#FAFAF9]/60 transition-colors h-[48px]"
                  >
                    <td className="px-5 py-3">
                      <p className="font-medium text-[#1C1917] truncate max-w-xs">
                        {tpl.name}
                      </p>
                    </td>
                    <td className="px-5 py-3">
                      <Badge variant="neutral" size="sm">
                        <span className="capitalize">{tpl.channel}</span>
                      </Badge>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex flex-wrap gap-1 max-w-sm">
                        {tpl.variables?.length ? (
                          tpl.variables.map((v) => (
                            <span
                              key={v}
                              className="px-1.5 py-0.5 bg-[#F5F5F4] border border-[#E7E5E4] rounded-[4px] text-[11px] font-mono text-[#1C1917]"
                            >
                              {`{{${v}}}`}
                            </span>
                          ))
                        ) : (
                          <span className="text-[#A8A29E] text-[11px]">None</span>
                        )}
                      </div>
                    </td>
                    <td className="px-5 py-3 text-[#78716C]">
                      {new Date(
                        tpl.updated_at || tpl.created_at
                      ).toLocaleDateString()}
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {canWrite ? (
                          <>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openEdit(tpl)}
                            >
                              Edit
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="text-[#B91C1C] hover:text-[#991B1B] hover:bg-[#FEF2F2]"
                              onClick={() => setDeleteTarget(tpl)}
                            >
                              Delete
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openView(tpl)}
                          >
                            View
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-3 bg-white">
            <Pagination
              total={total}
              page={page}
              pageSize={pageSize}
              onPageChange={setPage}
              onPageSizeChange={(s) => {
                setPageSize(s);
                setPage(1);
              }}
            />
          </div>
        </div>
      )}

      {/* Create / Edit / View Modal */}
      {modalMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="bg-white border border-[#E7E5E4] rounded-[12px] w-full max-w-xl max-h-[90vh] overflow-y-auto p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#E7E5E4]">
              <h2 className="text-base font-semibold text-[#1C1917]">
                {modalMode === 'create'
                  ? 'New Template'
                  : modalMode === 'edit'
                  ? 'Edit Template'
                  : 'View Template'}
              </h2>
              <button
                type="button"
                onClick={closeModal}
                className="p-1 rounded text-[#78716C] hover:text-[#1C1917]"
              >
                <X className="w-4 h-4" strokeWidth={1.5} />
              </button>
            </div>

            {formError && (
              <div className="px-3.5 py-2.5 rounded-[6px] bg-[#FEF2F2] border border-[#FECACA] text-[#B91C1C] text-xs">
                {formError}
              </div>
            )}

            <form onSubmit={handleSave} className="space-y-4">
              <Input
                id="template-name"
                label="Template Name *"
                type="text"
                required
                maxLength={100}
                disabled={modalMode === 'view'}
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g. Welcome Email"
              />

              <Select
                id="template-channel"
                label="Channel *"
                disabled={modalMode !== 'create'}
                value={formChannel}
                onChange={(e) => setFormChannel(e.target.value)}
                helper={
                  modalMode === 'edit'
                    ? 'Channel cannot be modified after creation.'
                    : undefined
                }
              >
                <option value="email">Email</option>
                <option value="sms">SMS</option>
              </Select>

              {formChannel === 'email' && (
                <Input
                  id="template-subject"
                  label="Subject Template"
                  type="text"
                  maxLength={255}
                  disabled={modalMode === 'view'}
                  value={formSubject}
                  onChange={(e) => setFormSubject(e.target.value)}
                  placeholder="Hello {{name}}, welcome to Notify!"
                />
              )}

              <div className="space-y-1.5">
                <div className="flex justify-between items-center">
                  <label
                    htmlFor="template-body"
                    className="block text-xs font-medium text-[#1C1917]"
                  >
                    Body Template *
                  </label>
                  <span
                    className={`text-[11px] ${
                      formBody.length > 10000
                        ? 'text-[#B91C1C] font-semibold'
                        : 'text-[#78716C]'
                    }`}
                  >
                    {formBody.length} / 10000
                  </span>
                </div>
                <textarea
                  id="template-body"
                  rows={6}
                  required
                  maxLength={10000}
                  disabled={modalMode === 'view'}
                  value={formBody}
                  onChange={(e) => setFormBody(e.target.value)}
                  placeholder="Use {{variable}} syntax for dynamic personalization..."
                  className="w-full font-mono text-xs px-3 py-2 rounded-[6px] bg-white border border-[#E7E5E4] text-[#1C1917] placeholder:text-[#A8A29E] focus:outline-none focus:ring-2 focus:ring-[#4F46E5]/20 focus:border-[#4F46E5] disabled:bg-[#F5F5F4]"
                />
              </div>

              {/* Detected Variables Live List */}
              <div className="space-y-1.5">
                <span className="block text-xs font-medium text-[#78716C]">
                  Detected Variables ({detectedVars.length})
                </span>
                <div className="flex flex-wrap gap-1.5 p-2.5 rounded-[6px] bg-[#FAFAF9] border border-[#E7E5E4] min-h-[36px]">
                  {detectedVars.length > 0 ? (
                    detectedVars.map((v) => (
                      <span
                        key={v}
                        className="px-2 py-0.5 bg-white text-[#4F46E5] border border-[#C7D2FE] rounded-[4px] text-xs font-mono"
                      >
                        {`{{${v}}}`}
                      </span>
                    ))
                  ) : (
                    <span className="text-[11px] text-[#A8A29E]">
                      No variables detected yet. Type with {'{{variable}}'}{' '}
                      format.
                    </span>
                  )}
                </div>
              </div>

              <div className="flex justify-end gap-2.5 pt-3 border-t border-[#E7E5E4]">
                <Button variant="secondary" size="sm" onClick={closeModal}>
                  {modalMode === 'view' ? 'Close' : 'Cancel'}
                </Button>
                {modalMode !== 'view' && (
                  <Button
                    type="submit"
                    variant="primary"
                    size="sm"
                    loading={saving}
                  >
                    {modalMode === 'create'
                      ? 'Create Template'
                      : 'Save Changes'}
                  </Button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        destructive
        title="Delete Template?"
        message={`Are you sure you want to delete "${deleteTarget?.name}"? Any automated jobs using this template will fail.`}
        confirmLabel="Delete"
        loading={deleting}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}
