import { useState, useEffect, useCallback } from 'react';
import { listTemplates, createTemplate, updateTemplate, deleteTemplate } from '../lib/api';
import { useAuth } from '../lib/auth';
import Pagination from '../components/Pagination';
import ConfirmDialog from '../components/ConfirmDialog';
import ErrorBanner from '../components/ErrorBanner';
import Loading from '../components/Loading';
import EmptyState from '../components/EmptyState';

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

  const detectedVars = extractVariables(formBody, formChannel === 'email' ? formSubject : '');

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
        subject_template: formChannel === 'email' ? formSubject.trim() || null : null,
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-bold">Templates</h1>
        {canWrite && (
          <button
            onClick={openCreate}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors"
          >
            + New Template
          </button>
        )}
      </div>

      {error && <ErrorBanner error={error} onRetry={fetchTemplates} />}

      {loading && templates.length === 0 ? (
        <Loading />
      ) : templates.length === 0 ? (
        <EmptyState message="No templates found. Create one to use with notifications." />
      ) : (
        <>
          <div className="overflow-x-auto rounded-xl border border-gray-800">
            <table className="w-full text-sm text-left">
              <thead className="bg-gray-900 text-gray-400">
                <tr>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Channel</th>
                  <th className="px-4 py-3">Variables</th>
                  <th className="px-4 py-3">Updated</th>
                  <th className="px-4 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800 font-sans">
                {templates.map((tpl) => (
                  <tr key={tpl.id} className="bg-gray-950 hover:bg-gray-900/60 transition-colors">
                    <td className="px-4 py-3 font-medium text-white max-w-xs truncate">{tpl.name}</td>
                    <td className="px-4 py-3 uppercase text-xs font-semibold text-gray-400">
                      <span className={`px-2 py-0.5 rounded-full border ${tpl.channel === 'email' ? 'border-blue-700 bg-blue-900/30 text-blue-300' : 'border-purple-700 bg-purple-900/30 text-purple-300'}`}>
                        {tpl.channel}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1 max-w-sm">
                        {tpl.variables?.length ? (
                          tpl.variables.map((v) => (
                            <span key={v} className="px-1.5 py-0.5 bg-gray-800 border border-gray-700 rounded text-xs font-mono text-gray-300">
                              {`{{${v}}}`}
                            </span>
                          ))
                        ) : (
                          <span className="text-gray-500 text-xs">None</span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">
                      {new Date(tpl.updated_at || tpl.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-2">
                        {canWrite ? (
                          <>
                            <button
                              onClick={() => openEdit(tpl)}
                              className="px-2.5 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => setDeleteTarget(tpl)}
                              className="px-2.5 py-1 text-xs rounded bg-red-950/40 hover:bg-red-900/60 text-red-300 border border-red-800"
                            >
                              Delete
                            </button>
                          </>
                        ) : (
                          <button
                            onClick={() => openView(tpl)}
                            className="px-2.5 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700"
                          >
                            View
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

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
        </>
      )}

      {/* Create / Edit / View Modal */}
      {modalMode && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-gray-800 pb-3">
              <h2 className="text-lg font-bold text-white">
                {modalMode === 'create'
                  ? 'New Template'
                  : modalMode === 'edit'
                  ? 'Edit Template'
                  : 'View Template'}
              </h2>
              <button onClick={closeModal} className="text-gray-400 hover:text-white text-lg">
                ✕
              </button>
            </div>

            {formError && (
              <div className="p-3 bg-red-950/40 border border-red-800 rounded-lg text-red-300 text-xs">
                {formError}
              </div>
            )}

            <form onSubmit={handleSave} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-gray-300 uppercase mb-1">
                  Template Name *
                </label>
                <input
                  type="text"
                  required
                  maxLength={100}
                  disabled={modalMode === 'view'}
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="e.g. Welcome Email"
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm disabled:opacity-60"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-300 uppercase mb-1">
                  Channel *
                </label>
                <select
                  disabled={modalMode !== 'create'}
                  value={formChannel}
                  onChange={(e) => setFormChannel(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm disabled:opacity-60"
                >
                  <option value="email">Email</option>
                  <option value="sms">SMS</option>
                </select>
                {modalMode === 'edit' && (
                  <p className="text-xs text-gray-500 mt-1">Channel cannot be modified after creation.</p>
                )}
              </div>

              {formChannel === 'email' && (
                <div>
                  <label className="block text-xs font-semibold text-gray-300 uppercase mb-1">
                    Subject Template
                  </label>
                  <input
                    type="text"
                    maxLength={255}
                    disabled={modalMode === 'view'}
                    value={formSubject}
                    onChange={(e) => setFormSubject(e.target.value)}
                    placeholder="Hello {{name}}, welcome!"
                    className="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm disabled:opacity-60"
                  />
                </div>
              )}

              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="block text-xs font-semibold text-gray-300 uppercase">
                    Body Template *
                  </label>
                  <span className={`text-xs ${formBody.length > 10000 ? 'text-red-400 font-bold' : 'text-gray-400'}`}>
                    {formBody.length} / 10000
                  </span>
                </div>
                <textarea
                  rows={6}
                  required
                  maxLength={10000}
                  disabled={modalMode === 'view'}
                  value={formBody}
                  onChange={(e) => setFormBody(e.target.value)}
                  placeholder="Use {{variable}} syntax for dynamic inputs..."
                  className="w-full font-mono px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-white text-sm disabled:opacity-60"
                />
              </div>

              {/* Detected Variables live list */}
              <div>
                <span className="block text-xs font-semibold text-gray-400 uppercase mb-1">
                  Detected Variables ({detectedVars.length})
                </span>
                <div className="flex flex-wrap gap-1 p-2 rounded-lg bg-gray-950 border border-gray-800 min-h-[36px]">
                  {detectedVars.length > 0 ? (
                    detectedVars.map((v) => (
                      <span key={v} className="px-2 py-0.5 bg-blue-950 text-blue-300 border border-blue-800 rounded text-xs font-mono">
                        {`{{${v}}}`}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-gray-500">None detected yet. Type with {'{{variable}}'} format.</span>
                  )}
                </div>
              </div>

              {/* Modal footer */}
              <div className="flex justify-end gap-3 pt-4 border-t border-gray-800">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm font-medium"
                >
                  {modalMode === 'view' ? 'Close' : 'Cancel'}
                </button>
                {modalMode !== 'view' && (
                  <button
                    type="submit"
                    disabled={saving}
                    className="px-5 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium disabled:opacity-50"
                  >
                    {saving ? 'Saving...' : modalMode === 'create' ? 'Create Template' : 'Save Changes'}
                  </button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete Template"
        message={`Are you sure you want to permanently delete template "${deleteTarget?.name}"?`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        loading={deleting}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  );
}

