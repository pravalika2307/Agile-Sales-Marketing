import * as React from "react";
import { cn } from "@/lib/utils";

export interface TableProps extends React.HTMLAttributes<HTMLTableElement> {
  containerClassName?: string;
}

const Table = React.forwardRef<HTMLTableElement, TableProps>(
  ({ className, containerClassName, ...props }, ref) => (
    <div
      className={cn(
        "relative w-full overflow-auto rounded-xl border border-slate-200/80 bg-white shadow-xs",
        containerClassName
      )}
    >
      <table
        ref={ref}
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
);
Table.displayName = "Table";

const TableHeader = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <thead
    ref={ref}
    className={cn(
      "bg-slate-50/80 border-b border-slate-200/90 text-[11px] font-semibold uppercase tracking-wider text-slate-500",
      className
    )}
    {...props}
  />
));
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tbody
    ref={ref}
    className={cn("[&_tr:last-child]:border-0 divide-y divide-slate-100", className)}
    {...props}
  />
));
TableBody.displayName = "TableBody";

const TableFooter = React.forwardRef<
  HTMLTableSectionElement,
  React.HTMLAttributes<HTMLTableSectionElement>
>(({ className, ...props }, ref) => (
  <tfoot
    ref={ref}
    className={cn(
      "bg-slate-50 font-medium text-slate-600 border-t border-slate-200",
      className
    )}
    {...props}
  />
));
TableFooter.displayName = "TableFooter";

const TableRow = React.forwardRef<
  HTMLTableRowElement,
  React.HTMLAttributes<HTMLTableRowElement>
>(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    className={cn(
      "border-b border-slate-100 transition-colors hover:bg-slate-50/70 data-[state=selected]:bg-[#fff6f0]/60",
      className
    )}
    {...props}
  />
));
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef<
  HTMLTableCellElement,
  React.ThHTMLAttributes<HTMLTableCellElement>
>(({ className, scope = "col", ...props }, ref) => (
  <th
    ref={ref}
    scope={scope}
    className={cn(
      "h-9 px-4 text-left align-middle font-semibold text-slate-500 [&:has([role=checkbox])]:pr-0",
      className
    )}
    {...props}
  />
));
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<
  HTMLTableCellElement,
  React.TdHTMLAttributes<HTMLTableCellElement>
>(({ className, ...props }, ref) => (
  <td
    ref={ref}
    className={cn(
      "p-3.5 sm:p-4 align-middle text-slate-700 text-xs md:text-sm [&:has([role=checkbox])]:pr-0",
      className
    )}
    {...props}
  />
));
TableCell.displayName = "TableCell";

interface TableLoadingRowProps {
  colSpan: number;
  rows?: number;
}

const TableLoadingRow: React.FC<TableLoadingRowProps> = ({ colSpan, rows = 3 }) => (
  <>
    {Array.from({ length: rows }).map((_, i) => (
      <TableRow key={i} className="hover:bg-transparent">
        <TableCell colSpan={colSpan} className="py-4">
          <div className="h-6 w-full rounded-md bg-slate-100 animate-pulse" />
        </TableCell>
      </TableRow>
    ))}
  </>
);
TableLoadingRow.displayName = "TableLoadingRow";

export interface TableEmptyRowProps {
  colSpan: number;
  title?: string;
  description?: string;
  icon?: React.ReactNode;
  action?: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}

const TableEmptyRow: React.FC<TableEmptyRowProps> = ({
  colSpan,
  title = "No data found",
  description = "No items match your active filters.",
  icon,
  action,
  actionLabel,
  onAction,
}) => {
  const resolvedAction =
    action ||
    (actionLabel && onAction ? (
      <button
        type="button"
        onClick={onAction}
        className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-xs font-semibold text-slate-700 shadow-2xs transition-colors"
      >
        {actionLabel}
      </button>
    ) : null);

  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colSpan} className="py-12 text-center">
        <div className="flex flex-col items-center justify-center space-y-1.5 max-w-sm mx-auto">
          {icon && <div className="mb-1">{icon}</div>}
          <span className="font-semibold text-slate-700 text-sm">{title}</span>
          <p className="text-xs text-slate-500">{description}</p>
          {resolvedAction && <div className="pt-2">{resolvedAction}</div>}
        </div>
      </TableCell>
    </TableRow>
  );
};
TableEmptyRow.displayName = "TableEmptyRow";

interface TableErrorRowProps {
  colSpan: number;
  title?: string;
  message?: string;
  onRetry?: () => void;
}

const TableErrorRow: React.FC<TableErrorRowProps> = ({
  colSpan,
  title = "Failed to load records",
  message = "Please check your network connection and try again.",
  onRetry,
}) => (
  <TableRow className="hover:bg-transparent">
    <TableCell colSpan={colSpan} className="py-10 text-center">
      <div className="flex flex-col items-center justify-center space-y-2 max-w-sm mx-auto text-rose-700">
        <span className="font-semibold text-sm">{title}</span>
        <p className="text-xs text-rose-600/90">{message}</p>
        {onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="text-xs font-semibold text-rose-800 underline hover:text-rose-950 pt-1"
          >
            Retry
          </button>
        )}
      </div>
    </TableCell>
  </TableRow>
);
TableErrorRow.displayName = "TableErrorRow";

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableLoadingRow,
  TableEmptyRow,
  TableErrorRow,
};
