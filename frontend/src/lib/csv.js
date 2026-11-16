/**
 * Robust CSV parser handling UTF-8 BOM, quoted cells with commas/escaped quotes,
 * CRLF/LF line endings, cell trimming, and blank line filtering.
 */
export function parseCSVRows(rawText) {
  if (!rawText) return [];

  // Strip UTF-8 BOM if present
  let text = rawText;
  if (text.charCodeAt(0) === 0xfeff) {
    text = text.slice(1);
  }

  const rows = [];
  let currentRow = [];
  let currentCell = '';
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];
    const nextChar = text[i + 1];

    if (inQuotes) {
      if (char === '"') {
        if (nextChar === '"') {
          // Escaped double quote
          currentCell += '"';
          i++;
        } else {
          // Closing quote
          inQuotes = false;
        }
      } else {
        currentCell += char;
      }
    } else {
      if (char === '"') {
        inQuotes = true;
      } else if (char === ',') {
        currentRow.push(currentCell.trim());
        currentCell = '';
      } else if (char === '\r') {
        if (nextChar === '\n') {
          i++;
        }
        currentRow.push(currentCell.trim());
        currentCell = '';
        if (currentRow.some((c) => c.length > 0)) {
          rows.push(currentRow);
        }
        currentRow = [];
      } else if (char === '\n') {
        currentRow.push(currentCell.trim());
        currentCell = '';
        if (currentRow.some((c) => c.length > 0)) {
          rows.push(currentRow);
        }
        currentRow = [];
      } else {
        currentCell += char;
      }
    }
  }

  // Final cell and row if not ended with newline
  currentRow.push(currentCell.trim());
  if (currentRow.some((c) => c.length > 0)) {
    rows.push(currentRow);
  }

  return rows;
}

export function validateEmail(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

export function validatePhone(phone) {
  return /^\+?\d{10,15}$/.test(phone);
}

export function parseRecipientsData(rawText, { channel = 'email', hasTemplate = false, templateVariables = [] } = {}) {
  const rows = parseCSVRows(rawText);
  if (rows.length === 0) {
    return {
      totalParsed: 0,
      rows: [],
      validRows: [],
      duplicateCount: 0,
      invalidCount: 0,
      missingVarCount: 0,
      headerError: hasTemplate ? 'CSV is empty. Header row starting with "recipient" is required.' : null,
      errors: ['No rows found in input.'],
    };
  }

  let dataRows = rows;
  let varColMap = {}; // varName -> colIndex
  let headerError = null;

  if (hasTemplate) {
    const header = rows[0];
    if (!header || header[0]?.toLowerCase() !== 'recipient') {
      return {
        totalParsed: rows.length,
        rows: [],
        validRows: [],
        duplicateCount: 0,
        invalidCount: 0,
        missingVarCount: 0,
        headerError: 'First column of the header row must be "recipient".',
        errors: ['First column of the header row must be "recipient".'],
      };
    }

    // Map remaining columns to variable names
    for (let c = 1; c < header.length; c++) {
      const colName = header[c]?.trim();
      if (colName) {
        varColMap[colName] = c;
      }
    }
    dataRows = rows.slice(1);
  } else {
    // If not using a template, check if row 0 has header "recipient"
    if (rows[0] && rows[0][0]?.toLowerCase() === 'recipient') {
      dataRows = rows.slice(1);
    }
  }

  const seenRecipients = new Set();
  let duplicateCount = 0;
  let invalidCount = 0;
  let missingVarCount = 0;

  const parsedList = [];
  const validList = [];

  for (let idx = 0; idx < dataRows.length; idx++) {
    const row = dataRows[idx];
    const recipient = row[0]?.trim() || '';

    // Validate recipient format
    const isValidFormat = channel === 'email' ? validateEmail(recipient) : validatePhone(recipient);
    if (!isValidFormat) {
      invalidCount++;
    }

    // Extract variables if template used
    let variables = undefined;
    let missingVars = [];
    if (hasTemplate) {
      variables = {};
      for (const v of templateVariables) {
        const colIdx = varColMap[v];
        const val = colIdx !== undefined && colIdx < row.length ? row[colIdx] : '';
        if (val === undefined || val === '') {
          missingVars.push(v);
        } else {
          variables[v] = val;
        }
      }
      if (missingVars.length > 0) {
        missingVarCount++;
      }
    }

    const rowObj = {
      index: idx + 1,
      recipient,
      isValid: isValidFormat,
      variables,
      missingVars,
      isDuplicate: false,
    };

    const lowerRecip = recipient.toLowerCase();
    if (seenRecipients.has(lowerRecip)) {
      rowObj.isDuplicate = true;
      duplicateCount++;
    } else {
      if (recipient) seenRecipients.add(lowerRecip);
      if (isValidFormat && (!hasTemplate || missingVars.length === 0)) {
        validList.push({
          recipient,
          variables,
        });
      }
    }

    parsedList.push(rowObj);
  }

  const blockingErrors = [];
  if (dataRows.length === 0) {
    blockingErrors.push('No recipient rows found.');
  }
  if (dataRows.length > 200) {
    blockingErrors.push(`Limit exceeded: ${dataRows.length} recipients parsed before de-duplication (max 200 allowed).`);
  }
  if (invalidCount > 0) {
    blockingErrors.push(`${invalidCount} recipient(s) have invalid ${channel.toUpperCase()} formatting.`);
  }
  if (missingVarCount > 0) {
    blockingErrors.push(`${missingVarCount} row(s) are missing one or more required template variables.`);
  }
  if (validList.length === 0 && dataRows.length > 0) {
    blockingErrors.push('No valid recipients to send.');
  }

  return {
    totalParsed: dataRows.length,
    rows: parsedList,
    validRows: validList,
    duplicateCount,
    invalidCount,
    missingVarCount,
    headerError,
    errors: blockingErrors,
  };
}

