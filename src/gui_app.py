from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from src.file_pipeline import (
    FileProcessingResult,
    process_input_directory,
    process_text_content,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIR = PROJECT_ROOT / "data" / "input"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "output"


@dataclass(frozen=True)
class SummaryCounts:
    total: int
    processed: int
    skipped: int
    errors: int


def summarize_results(results: list[FileProcessingResult]) -> SummaryCounts:
    return SummaryCounts(
        total=len(results),
        processed=sum(result.status == "processed" for result in results),
        skipped=sum(result.status == "skipped" for result in results),
        errors=sum(result.status == "error" for result in results),
    )


def format_result_line(result: FileProcessingResult) -> str:
    details = [result.input_path, result.detected_kind, result.status]
    if result.output_path:
        details.append(f"output={result.output_path}")
    if result.report_path:
        details.append(f"report={result.report_path}")
    if result.message:
        details.append(result.message)
    return " | ".join(details)


def build_result_detail(result: FileProcessingResult, preview_chars: int = 900) -> str:
    lines = [
        f"Input: {result.input_path}",
        f"Kind: {result.detected_kind}",
        f"Status: {result.status}",
        f"Policy: {result.policy_name}",
    ]
    if result.output_path:
        lines.append(f"Output: {result.output_path}")
    if result.report_path:
        lines.append(f"Report: {result.report_path}")
    if result.message:
        lines.append(f"Message: {result.message}")

    if result.output_path and Path(result.output_path).exists():
        try:
            preview = Path(result.output_path).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:  # pragma: no cover - filesystem error path
            lines.append(f"Preview error: {exc}")
        else:
            preview = preview.strip()
            if preview:
                lines.append("")
                lines.append("Preview:")
                lines.append(preview[:preview_chars])

    return "\n".join(lines)


def open_folder(path: str | Path) -> None:
    folder = Path(path)
    if not folder.exists():
        raise FileNotFoundError(f"Path does not exist: {folder}")

    if hasattr(os, "startfile"):
        os.startfile(str(folder))  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        subprocess.run(["open", str(folder)], check=False)
        return

    subprocess.run(["xdg-open", str(folder)], check=False)


class AnonymizationApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Industrial Data Anonymization Filters")
        self.geometry("1080x780")
        self.minsize(960, 680)

        self.text_policy_var = tk.StringVar(value="light")
        self.batch_policy_var = tk.StringVar(value="light")
        self.batch_input_var = tk.StringVar(value=str(DEFAULT_INPUT_DIR))
        self.batch_output_var = tk.StringVar(value=str(DEFAULT_OUTPUT_DIR))
        self.recursive_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ready")
        self.batch_summary_var = tk.StringVar(value="No batch run yet")
        self.batch_selection_var = tk.StringVar(value="Select a batch result to preview it here")
        self.batch_results: list[FileProcessingResult] = []

        self._build_ui()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        notebook = ttk.Notebook(self)
        notebook.grid(row=0, column=0, sticky="nsew")

        self.text_tab = ttk.Frame(notebook, padding=12)
        self.batch_tab = ttk.Frame(notebook, padding=12)
        self.log_tab = ttk.Frame(notebook, padding=12)

        notebook.add(self.batch_tab, text="Folder Batch")
        notebook.add(self.text_tab, text="Text")
        notebook.add(self.log_tab, text="Status")

        self._build_text_tab()
        self._build_batch_tab()
        self._build_log_tab()

        status_bar = ttk.Label(self, textvariable=self.status_var, anchor="w")
        status_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))

    def _build_text_tab(self) -> None:
        self.text_tab.columnconfigure(1, weight=1)
        self.text_tab.rowconfigure(1, weight=1)

        ttk.Label(self.text_tab, text="Policy").grid(row=0, column=0, sticky="w")
        policy_box = ttk.Combobox(
            self.text_tab,
            textvariable=self.text_policy_var,
            values=("light", "strict"),
            state="readonly",
            width=12,
        )
        policy_box.grid(row=0, column=1, sticky="w", pady=(0, 8))

        ttk.Label(self.text_tab, text="Input text").grid(row=1, column=0, sticky="nw")
        self.text_input = tk.Text(self.text_tab, height=14, wrap="word")
        self.text_input.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))

        action_row = ttk.Frame(self.text_tab)
        action_row.grid(row=2, column=1, sticky="w", padx=(8, 0), pady=(0, 8))
        ttk.Button(action_row, text="Anonymize Text", command=self._run_text_anonymization).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(action_row, text="Load Sample", command=self._load_sample_text).grid(row=0, column=1)

        ttk.Label(self.text_tab, text="Output").grid(row=3, column=0, sticky="nw")
        self.text_output = tk.Text(self.text_tab, height=14, wrap="word", state="disabled")
        self.text_output.grid(row=3, column=1, sticky="nsew", padx=(8, 0))

    def _build_batch_tab(self) -> None:
        self.batch_tab.columnconfigure(1, weight=1)
        self.batch_tab.rowconfigure(6, weight=1)
        self.batch_tab.rowconfigure(8, weight=1)

        ttk.Label(self.batch_tab, text="Policy").grid(row=0, column=0, sticky="w", pady=(0, 8))
        policy_box = ttk.Combobox(
            self.batch_tab,
            textvariable=self.batch_policy_var,
            values=("light", "strict"),
            state="readonly",
            width=12,
        )
        policy_box.grid(row=0, column=1, sticky="w", pady=(0, 8))

        ttk.Label(self.batch_tab, text="Input folder").grid(row=1, column=0, sticky="w", pady=(0, 8))
        input_row = ttk.Frame(self.batch_tab)
        input_row.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        input_row.columnconfigure(0, weight=1)
        ttk.Entry(input_row, textvariable=self.batch_input_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(input_row, text="Browse", command=self._choose_input_folder).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(self.batch_tab, text="Output folder").grid(row=2, column=0, sticky="w", pady=(0, 8))
        output_row = ttk.Frame(self.batch_tab)
        output_row.grid(row=2, column=1, sticky="ew", pady=(0, 8))
        output_row.columnconfigure(0, weight=1)
        ttk.Entry(output_row, textvariable=self.batch_output_var).grid(row=0, column=0, sticky="ew")
        ttk.Button(output_row, text="Browse", command=self._choose_output_folder).grid(row=0, column=1, padx=(8, 0))

        ttk.Checkbutton(self.batch_tab, text="Recursive", variable=self.recursive_var).grid(row=3, column=1, sticky="w", pady=(0, 12))

        action_row = ttk.Frame(self.batch_tab)
        action_row.grid(row=4, column=1, sticky="w")
        ttk.Button(action_row, text="Run Folder Batch", command=self._run_folder_batch).grid(row=0, column=0, padx=(0, 8))
        ttk.Button(action_row, text="Reset Defaults", command=self._reset_default_folders).grid(row=0, column=1)
        ttk.Button(action_row, text="Open Input Folder", command=self._open_input_folder).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(action_row, text="Open Output Folder", command=self._open_output_folder).grid(row=0, column=3, padx=(8, 0))

        summary_frame = ttk.LabelFrame(self.batch_tab, text="Batch Summary", padding=10)
        summary_frame.grid(row=5, column=1, sticky="ew", pady=(16, 8))
        summary_frame.columnconfigure(0, weight=1)
        ttk.Label(summary_frame, textvariable=self.batch_summary_var).grid(row=0, column=0, sticky="w")

        results_frame = ttk.LabelFrame(self.batch_tab, text="Results", padding=10)
        results_frame.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)

        self.batch_tree = ttk.Treeview(
            results_frame,
            columns=("kind", "status", "output", "report"),
            show="headings",
            selectmode="browse",
            height=8,
        )
        for column, heading, width in (
            ("kind", "Kind", 100),
            ("status", "Status", 100),
            ("output", "Output", 320),
            ("report", "Report", 280),
        ):
            self.batch_tree.heading(column, text=heading)
            self.batch_tree.column(column, width=width, anchor="w")
        self.batch_tree.grid(row=0, column=0, sticky="nsew")
        self.batch_tree.bind("<<TreeviewSelect>>", self._on_batch_tree_select)

        tree_scroll = ttk.Scrollbar(results_frame, command=self.batch_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.batch_tree.configure(yscrollcommand=tree_scroll.set)

        detail_frame = ttk.LabelFrame(self.batch_tab, text="Selected Result Preview", padding=10)
        detail_frame.grid(row=8, column=0, columnspan=2, sticky="nsew")
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(0, weight=1)

        self.batch_detail_text = tk.Text(detail_frame, wrap="word", state="disabled", height=12)
        self.batch_detail_text.grid(row=0, column=0, sticky="nsew")
        detail_scroll = ttk.Scrollbar(detail_frame, command=self.batch_detail_text.yview)
        detail_scroll.grid(row=0, column=1, sticky="ns")
        self.batch_detail_text.configure(yscrollcommand=detail_scroll.set)

        help_text = (
            f"Default input: {DEFAULT_INPUT_DIR}\n"
            f"Default output: {DEFAULT_OUTPUT_DIR}\n"
            "Files are anonymized into the output folder and each run writes a per-file report."
        )
        ttk.Label(self.batch_tab, text=help_text, justify="left").grid(row=7, column=1, sticky="w", pady=(0, 8))

    def _build_log_tab(self) -> None:
        self.log_tab.rowconfigure(0, weight=1)
        self.log_tab.columnconfigure(0, weight=1)

        self.log_text = tk.Text(self.log_tab, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(self.log_tab, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

    def _load_sample_text(self) -> None:
        self.text_input.delete("1.0", tk.END)
        self.text_input.insert(
            tk.END,
            "Operator: John Carter | Email: john.carter@acme.com | Phone: +358401234567\n"
            "Location: Helsinki Plant | Badge ID: ABC-12345",
        )
        self._set_status("Loaded sample text")

    def _choose_input_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.batch_input_var.get() or str(DEFAULT_INPUT_DIR))
        if folder:
            self.batch_input_var.set(folder)
            self._set_status(f"Input folder set: {folder}")

    def _choose_output_folder(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.batch_output_var.get() or str(DEFAULT_OUTPUT_DIR))
        if folder:
            self.batch_output_var.set(folder)
            self._set_status(f"Output folder set: {folder}")

    def _reset_default_folders(self) -> None:
        self.batch_input_var.set(str(DEFAULT_INPUT_DIR))
        self.batch_output_var.set(str(DEFAULT_OUTPUT_DIR))
        self.recursive_var.set(True)
        self._set_status("Reset to default folders")

    def _run_text_anonymization(self) -> None:
        input_text = self.text_input.get("1.0", tk.END).strip()
        if not input_text:
            messagebox.showinfo("No input", "Enter some text to anonymize first.")
            return

        try:
            result_text, results, config = process_text_content(input_text, self.text_policy_var.get())
        except Exception as exc:  # pragma: no cover - GUI error path
            messagebox.showerror("Text anonymization failed", str(exc))
            self._append_log(f"Text anonymization failed: {exc}")
            return

        self._set_text_output(result_text)
        self._set_status(f"Text anonymized with {config['policy_name']} policy ({len(results)} detections)")
        self._append_log(
            f"TEXT | policy={config['policy_name']} | detections={len(results)} | output={result_text}"
        )

    def _run_folder_batch(self) -> None:
        input_dir = Path(self.batch_input_var.get()).expanduser()
        output_dir = Path(self.batch_output_var.get()).expanduser()

        if not input_dir.exists():
            messagebox.showerror("Invalid input folder", f"Input folder does not exist: {input_dir}")
            return

        output_dir.mkdir(parents=True, exist_ok=True)
        self._set_status("Processing folder batch...")
        self._append_log(f"BATCH | started | input={input_dir} | output={output_dir}")

        thread = threading.Thread(
            target=self._process_folder_batch,
            args=(input_dir, output_dir, self.batch_policy_var.get(), self.recursive_var.get()),
            daemon=True,
        )
        thread.start()

    def _process_folder_batch(self, input_dir: Path, output_dir: Path, policy_name: str, recursive: bool) -> None:
        try:
            results = process_input_directory(
                input_dir,
                policy_name=policy_name,
                output_dir=output_dir,
                recursive=recursive,
            )
        except Exception as exc:  # pragma: no cover - GUI error path
            self.after(0, lambda: self._handle_batch_error(exc))
            return

        self.after(0, lambda: self._handle_batch_complete(results, input_dir, output_dir, policy_name, recursive))

    def _handle_batch_error(self, exc: Exception) -> None:
        messagebox.showerror("Folder batch failed", str(exc))
        self._set_status("Folder batch failed")
        self._append_log(f"BATCH | failed | {exc}")

    def _handle_batch_complete(
        self,
        results: list[FileProcessingResult],
        input_dir: Path,
        output_dir: Path,
        policy_name: str,
        recursive: bool,
    ) -> None:
        self.batch_results = results
        counts = summarize_results(results)
        self.batch_summary_var.set(
            f"Total: {counts.total} | Processed: {counts.processed} | Skipped: {counts.skipped} | Errors: {counts.errors}"
        )
        self._populate_results_table(results)
        self._show_batch_detail(
            f"Batch finished for {input_dir}\nOutput folder: {output_dir}\nPolicy: {policy_name}\nRecursive: {recursive}\n\nSelect a result row to preview its details."
        )
        self._set_status(
            f"Folder batch complete: {counts.processed} processed, {counts.skipped} skipped, {counts.errors} errors"
        )
        self._append_log(
            f"BATCH | complete | policy={policy_name} | recursive={recursive} | total={counts.total} | processed={counts.processed} | skipped={counts.skipped} | errors={counts.errors}"
        )
        for result in results:
            self._append_log(format_result_line(result))
        if not results:
            self._append_log(f"BATCH | no files found | input={input_dir} | output={output_dir}")

    def _populate_results_table(self, results: list[FileProcessingResult]) -> None:
        for row in self.batch_tree.get_children():
            self.batch_tree.delete(row)

        for index, result in enumerate(results):
            self.batch_tree.insert(
                "",
                tk.END,
                iid=str(index),
                values=(
                    result.detected_kind,
                    result.status,
                    result.output_path or "-",
                    result.report_path or "-",
                ),
            )

        if results:
            self.batch_tree.selection_set("0")
            self.batch_tree.focus("0")
            self._show_batch_detail(build_result_detail(results[0]))
        else:
            self._show_batch_detail("No files were processed.")

    def _on_batch_tree_select(self, _event: tk.Event) -> None:
        selection = self.batch_tree.selection()
        if not selection:
            return

        index = int(selection[0])
        if 0 <= index < len(self.batch_results):
            self._set_status(f"Selected result: {self.batch_results[index].input_path}")
            self._show_batch_detail(build_result_detail(self.batch_results[index]))

    def _show_batch_detail(self, value: str) -> None:
        self.batch_detail_text.configure(state="normal")
        self.batch_detail_text.delete("1.0", tk.END)
        self.batch_detail_text.insert(tk.END, value)
        self.batch_detail_text.configure(state="disabled")

    def _open_output_folder(self) -> None:
        folder = Path(self.batch_output_var.get()).expanduser()
        if not folder.exists():
            messagebox.showinfo("Folder missing", f"Output folder does not exist yet: {folder}")
            self._set_status(f"Output folder missing: {folder}")
            return

        try:
            open_folder(folder)
            self._set_status(f"Opened output folder: {folder}")
        except Exception as exc:  # pragma: no cover - platform/file-manager path
            messagebox.showerror("Unable to open folder", str(exc))
            self._set_status(f"Failed to open output folder: {folder}")

    def _open_input_folder(self) -> None:
        folder = Path(self.batch_input_var.get()).expanduser()
        if not folder.exists():
            messagebox.showinfo("Folder missing", f"Input folder does not exist: {folder}")
            self._set_status(f"Input folder missing: {folder}")
            return

        try:
            open_folder(folder)
            self._set_status(f"Opened input folder: {folder}")
        except Exception as exc:  # pragma: no cover - platform/file-manager path
            messagebox.showerror("Unable to open folder", str(exc))
            self._set_status(f"Failed to open input folder: {folder}")

    def _set_text_output(self, value: str) -> None:
        self.text_output.configure(state="normal")
        self.text_output.delete("1.0", tk.END)
        self.text_output.insert(tk.END, value)
        self.text_output.configure(state="disabled")

    def _append_log(self, value: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, f"[{timestamp}] {value}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _set_status(self, value: str) -> None:
        self.status_var.set(value)
        self._append_log(f"STATUS | {value}")


def launch_app() -> None:
    app = AnonymizationApp()
    app.mainloop()