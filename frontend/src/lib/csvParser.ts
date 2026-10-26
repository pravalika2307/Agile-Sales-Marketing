/**
 * Robust RFC 4180 CSV parser and column auto-mapping helper.
 * Strictly zero-dependency. Handles quotes, escaped quotes, newlines, commas, and BOM.
 */

export interface ParsedCSVData {
  headers: string[];
  rows: string[][];
  totalRows: number;
}

export interface ColumnMapping {
  first_name: number; // -1 if not mapped
  last_name: number;
  email: number;
  company_name: number;
  phone: number;
  job_title: number;
  industry: number;
  address_line_1: number;
  address_line_2: number;
  city: number;
  state: number;
  postal_code: number;
  country: number;
}

export const DEFAULT_COLUMN_MAPPING: ColumnMapping = {
  first_name: -1,
  last_name: -1,
  email: -1,
  company_name: -1,
  phone: -1,
  job_title: -1,
  industry: -1,
  address_line_1: -1,
  address_line_2: -1,
  city: -1,
  state: -1,
  postal_code: -1,
  country: -1,
};

export function parseCSV(csvText: string): ParsedCSVData {
  // Strip UTF-8 BOM if present
  const text = csvText.replace(/^\uFEFF/, "");

  const rows: string[][] = [];
  let currentRow: string[] = [];
  let currentField = "";
  let inQuotes = false;
  let i = 0;

  while (i < text.length) {
    const char = text[i];
    const nextChar = text[i + 1];

    if (inQuotes) {
      if (char === '"') {
        if (nextChar === '"') {
          currentField += '"';
          i += 2;
          continue;
        } else {
          inQuotes = false;
          i++;
          continue;
        }
      } else {
        currentField += char;
        i++;
        continue;
      }
    } else {
      if (char === '"') {
        inQuotes = true;
        i++;
        continue;
      } else if (char === ',') {
        currentRow.push(currentField.trim());
        currentField = "";
        i++;
        continue;
      } else if (char === '\r') {
        if (nextChar === '\n') {
          i++;
        }
        currentRow.push(currentField.trim());
        if (currentRow.some((val) => val.length > 0)) {
          rows.push(currentRow);
        }
        currentRow = [];
        currentField = "";
        i++;
        continue;
      } else if (char === '\n') {
        currentRow.push(currentField.trim());
        if (currentRow.some((val) => val.length > 0)) {
          rows.push(currentRow);
        }
        currentRow = [];
        currentField = "";
        i++;
        continue;
      } else {
        currentField += char;
        i++;
        continue;
      }
    }
  }

  // Final field and row
  if (currentField.length > 0 || currentRow.length > 0) {
    currentRow.push(currentField.trim());
    if (currentRow.some((val) => val.length > 0)) {
      rows.push(currentRow);
    }
  }

  if (rows.length === 0) {
    return { headers: [], rows: [], totalRows: 0 };
  }

  const headers = rows[0].map((h) => h.replace(/^["']|["']$/g, "").trim());
  const dataRows = rows.slice(1);

  return { headers, rows: dataRows, totalRows: dataRows.length };
}

/**
 * Auto-detect column mappings from headers using common naming patterns.
 */
export function autoDetectColumnMapping(headers: string[]): ColumnMapping {
  const mapping: ColumnMapping = { ...DEFAULT_COLUMN_MAPPING };

  headers.forEach((header, idx) => {
    const norm = header.toLowerCase().replace(/[^a-z0-9]/g, "");

    if (mapping.first_name === -1 && (norm === "firstname" || norm === "fname" || norm === "givenname" || norm === "first")) {
      mapping.first_name = idx;
    } else if (mapping.last_name === -1 && (norm === "lastname" || norm === "lname" || norm === "surname" || norm === "familyname" || norm === "last")) {
      mapping.last_name = idx;
    } else if (mapping.email === -1 && (norm === "email" || norm === "emailaddress" || norm === "mail" || norm === "workemail")) {
      mapping.email = idx;
    } else if (mapping.company_name === -1 && (norm === "company" || norm === "companyname" || norm === "organization" || norm === "org" || norm === "account" || norm === "business")) {
      mapping.company_name = idx;
    } else if (mapping.phone === -1 && (norm === "phone" || norm === "phonenumber" || norm === "telephone" || norm === "mobile" || norm === "workphone")) {
      mapping.phone = idx;
    } else if (mapping.job_title === -1 && (norm === "jobtitle" || norm === "title" || norm === "role" || norm === "position" || norm === "designation")) {
      mapping.job_title = idx;
    } else if (mapping.industry === -1 && (norm === "industry" || norm === "sector" || norm === "vertical")) {
      mapping.industry = idx;
    } else if (mapping.address_line_1 === -1 && (norm === "addressline1" || norm === "address1" || norm === "streetaddress" || norm === "street" || norm === "address" || norm === "addr1" || norm === "addr")) {
      mapping.address_line_1 = idx;
    } else if (mapping.address_line_2 === -1 && (norm === "addressline2" || norm === "address2" || norm === "suite" || norm === "apt" || norm === "unit" || norm === "bldg" || norm === "building" || norm === "addr2")) {
      mapping.address_line_2 = idx;
    } else if (mapping.city === -1 && (norm === "city" || norm === "location" || norm === "metro" || norm === "town")) {
      mapping.city = idx;
    } else if (mapping.state === -1 && (norm === "state" || norm === "province" || norm === "region" || norm === "st")) {
      mapping.state = idx;
    } else if (mapping.postal_code === -1 && (norm === "postalcode" || norm === "zip" || norm === "zipcode" || norm === "postcode" || norm === "postal" || norm === "zip4")) {
      mapping.postal_code = idx;
    } else if (mapping.country === -1 && (norm === "country" || norm === "nation")) {
      mapping.country = idx;
    }
  });

  return mapping;
}
