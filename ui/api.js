/* RPM Generator, API client.
   Satu-satunya penghubung ke backend nyata. Tanpa data palsu,
   tanpa fallback. Base URL via window.MODULE_API_BASE. */
(function () {
  'use strict';

  var BASE = (window.MODULE_API_BASE || '').replace(/\/$/, '');

  function request(method, path, body) {
    var opts = { method: method, headers: { Accept: 'application/json' } };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    return fetch(BASE + path, opts).then(function (res) {
      return res.json().catch(function () { return {}; }).then(function (data) {
        if (!res.ok) {
          var err = new Error('HTTP ' + res.status);
          err.status = res.status;
          err.data = data;
          throw err;
        }
        return data;
      });
    });
  }

  window.Api = {
    getCurriculumOptions: function () {
      return request('GET', '/api/curriculum/options');
    },
    generateContext: function (params) {
      return request('POST', '/api/context/generate', params);
    },
    generateModuleAsync: function (params) {
      return request('POST', '/api/module/generate',
        Object.assign({ async: true }, params));
    },
    getGenerationStatus: function (jobId) {
      return request('GET', '/api/generation/status/' + encodeURIComponent(jobId));
    },
    getModule: function (generationId) {
      return request('GET', '/api/module/' + encodeURIComponent(generationId));
    },
    listModules: function () {
      return request('GET', '/api/modules');
    },
    daftarBuku: function () {
      return request('GET', '/api/buku');
    },
    uploadBuku: function (file) {
      var fd = new FormData();
      fd.append('file', file);
      return fetch(BASE + '/api/buku/upload', {
        method: 'POST', body: fd,
        headers: { Accept: 'application/json' }
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            var err = new Error('HTTP ' + res.status);
            err.status = res.status;
            err.data = data;
            throw err;
          }
          return data;
        });
      });
    },
    listGenerations: function () {
      return request('GET', '/api/generations');
    },
    getGenerationLog: function (generationId) {
      return request('GET', '/api/generations/' +
        encodeURIComponent(generationId));
    },
    deleteModule: function (generationId) {
      return request('DELETE', '/api/modules/' +
        encodeURIComponent(generationId));
    },
    deleteGenerationLog: function (generationId) {
      return request('DELETE', '/api/generations/' +
        encodeURIComponent(generationId));
    },
    deleteGenerationLogs: function (generationIds) {
      return request('DELETE', '/api/generations',
        { generation_ids: generationIds });
    },
    deleteVersion: function (generationId, versionNo) {
      return request('DELETE', '/api/module/' +
        encodeURIComponent(generationId) + '/versions/' +
        encodeURIComponent(versionNo));
    },
    archiveModule: function (generationId) {
      return request('POST', '/api/modules/' +
        encodeURIComponent(generationId) + '/archive', {});
    },
    unarchiveModule: function (generationId) {
      return request('POST', '/api/modules/' +
        encodeURIComponent(generationId) + '/unarchive', {});
    },
    uploadModule: function (file) {
      var fd = new FormData();
      fd.append('file', file);
      return fetch(BASE + '/api/modules/import', {
        method: 'POST', body: fd,
        headers: { Accept: 'application/json' }
      }).then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          if (!res.ok) {
            var err = new Error('HTTP ' + res.status);
            err.status = res.status;
            err.data = data;
            throw err;
          }
          return data;
        });
      });
    },
    getStats: function () {
      return request('GET', '/api/stats');
    },
    exportDocxUrl: function (generationId) {
      return BASE + '/api/module/' + encodeURIComponent(generationId) +
        '/export-docx';
    },
    listVersions: function (generationId) {
      return request('GET', '/api/module/' + encodeURIComponent(generationId) +
        '/versions');
    },
    getVersion: function (generationId, versionNo) {
      return request('GET', '/api/module/' + encodeURIComponent(generationId) +
        '/versions/' + encodeURIComponent(versionNo));
    },
    saveVersion: function (generationId, baseVersion, changes) {
      return request('POST', '/api/module/' + encodeURIComponent(generationId) +
        '/versions', { base_version: baseVersion, changes: changes });
    },
    saveCandidate: function (generationId, baseVersion, candidate, changes) {
          return request('POST', '/api/module/' + encodeURIComponent(generationId) +
            '/versions', { base_version: baseVersion, candidate: candidate,
              changes: changes });
    },
    restoreVersion: function (generationId, versionNo) {
      return request('POST', '/api/module/' + encodeURIComponent(generationId) +
        '/versions/' + encodeURIComponent(versionNo) + '/restore', {});
    },
    regenerateSection: function (generationId, baseVersion, target,
        counts, extra) {
      var body = { base_version: baseVersion, target: target, async: true };
      if (counts && typeof counts === 'object') body.counts = counts;
      body.draft = true;
      if (extra && typeof extra === 'object') {
        for (var k in extra) {
          if (Object.prototype.hasOwnProperty.call(extra, k)) {
            body[k] = extra[k];
          }
        }
      }
      return request('POST', '/api/module/' + encodeURIComponent(generationId) +
        '/regenerate', body).then(function (accepted) {
        if (!accepted.job_id) return accepted;
        return new Promise(function (resolve, reject) {
          var tries = 0;
          function poll() {
            request('GET', '/api/generation/status/' +
              encodeURIComponent(accepted.job_id)).then(function (result) {
              if (result.status === 'running') {
                tries += 1;
                window.setTimeout(poll, Math.min(1000 + tries * 500, 5000));
                return;
              }
              if (result.status === 'success') resolve(result);
              else reject({ status: 422, data: result });
            }, reject);
          }
          poll();
        });
      });
    },
    finalizeVersion: function (generationId) {
      return request('POST', '/api/module/' + encodeURIComponent(generationId) +
        '/finalize', {});
    }
  };
})();
