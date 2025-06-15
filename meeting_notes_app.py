import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import re
import os
from datetime import datetime
from typing import List, Dict
import threading

# Spacy imports with fallback
try:
    import spacy
    SPACY_AVAILABLE = True
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        SPACY_AVAILABLE = False
        print("Spacy model 'en_core_web_sm' not found. Using fallback NLP.")
except ImportError:
    SPACY_AVAILABLE = False
    print("Spacy not installed. Using fallback NLP.")

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    print("python-docx not installed. DOCX files won't be supported.")


class MeetingNotesAnalyzer:
    def __init__(self):
        # Fallback patterns for when Spacy is not available
        self.action_patterns = [
            r'\b(?:will|should|must|need to|have to|going to)\s+([^.!?]+)',
            r'\b(?:action|task|todo|follow up|next step)[:]\s*([^.!?]+)',
            r'\b([A-Z][a-z]+\s+(?:will|should|must|needs to))\s+([^.!?]+)',
            r'\b(?:assign|delegate|responsible for)\s+([^.!?]+)',
        ]
        
        self.decision_patterns = [
            r'\b(?:decided|agreed|resolved|concluded|determined)\s+(?:to|that)\s+([^.!?]+)',
            r'\b(?:we|they|it was)\s+(?:decided|agreed|resolved)\s+([^.!?]+)',
            r'\b(?:decision|conclusion|agreement)[:]\s*([^.!?]+)',
            r'\b(?:final|official)\s+(?:decision|call|verdict)\s+([^.!?]+)',
        ]
        
        self.question_patterns = [
            r'([^.!?]*\?)',
            r'\b(?:question|ask|wondering|unclear|unsure)\s+(?:about|if|whether)\s+([^.!?]+)',
            r'\b(?:what|how|when|where|why|who)\s+([^.!?]+\?)',
            r'\b(?:need to clarify|need clarification|open item)\s+([^.!?]+)',
        ]

    def analyze_with_spacy(self, text: str) -> Dict[str, List[str]]:
        """Analyze text using Spacy NLP with enhanced logic"""
        if not SPACY_AVAILABLE:
            return self.analyze_with_patterns(text)
        
        doc = nlp(text)
        results = {"actions": [], "decisions": [], "questions": []}
        
        sentences = [sent.text.strip() for sent in doc.sents if sent.text.strip()]
        
        for sentence in sentences:
            sentence_doc = nlp(sentence)
            
            # Analyze sentence structure
            is_question = self._is_question(sentence, sentence_doc)
            is_decision = self._is_decision(sentence, sentence_doc)
            is_action = self._is_action(sentence, sentence_doc)
            
            # Categorize (questions take priority, then decisions, then actions)
            if is_question:
                results["questions"].append(sentence)
            elif is_decision:
                results["decisions"].append(sentence)
            elif is_action:
                results["actions"].append(sentence)
        
        # Remove duplicates while preserving order
        for key in results:
            results[key] = list(dict.fromkeys(results[key]))
        
        return results

    def _is_question(self, sentence: str, doc) -> bool:
        """Enhanced question detection using Spacy"""
        # Direct question marks
        if '?' in sentence:
            return True
        
        # Question words at the start
        question_words = ['what', 'how', 'when', 'where', 'why', 'who', 'which', 'whose']
        first_token = doc[0].text.lower() if doc else ""
        if first_token in question_words:
            return True
        
        # Uncertainty indicators
        uncertainty_phrases = ['unclear', 'unsure', 'not sure', 'question', 'wondering', 
                              'need clarification', 'open item', 'to be determined', 'tbd']
        sentence_lower = sentence.lower()
        if any(phrase in sentence_lower for phrase in uncertainty_phrases):
            return True
        
        # Check for auxiliary verbs that might indicate questions
        aux_verbs = ['do', 'does', 'did', 'can', 'could', 'will', 'would', 'should']
        if doc and doc[0].text.lower() in aux_verbs and doc[0].pos_ == 'AUX':
            return True
        
        return False

    def _is_decision(self, sentence: str, doc) -> bool:
        """Enhanced decision detection using Spacy"""
        decision_verbs = ['decided', 'agreed', 'resolved', 'concluded', 'determined', 
                         'approved', 'confirmed', 'finalized', 'settled']
        decision_nouns = ['decision', 'agreement', 'resolution', 'conclusion', 
                         'approval', 'confirmation', 'verdict', 'ruling']
        
        sentence_lower = sentence.lower()
        
        # Check for decision verbs
        if any(verb in sentence_lower for verb in decision_verbs):
            return True
        
        # Check for decision nouns
        if any(noun in sentence_lower for noun in decision_nouns):
            return True
        
        # Check for passive voice decisions
        passive_indicators = ['it was decided', 'it was agreed', 'it was resolved']
        if any(indicator in sentence_lower for indicator in passive_indicators):
            return True
        
        # Use Spacy to find past tense verbs that might indicate decisions
        for token in doc:
            if token.pos_ == 'VERB' and token.tag_ in ['VBD', 'VBN']:  # Past tense verbs
                if token.lemma_ in decision_verbs:
                    return True
        
        return False

    def _is_action(self, sentence: str, doc) -> bool:
        """Enhanced action item detection using Spacy"""
        action_indicators = ['will', 'should', 'must', 'need to', 'have to', 'going to',
                           'action', 'task', 'todo', 'assign', 'responsible', 'follow up',
                           'next step', 'deliverable', 'owner']
        
        sentence_lower = sentence.lower()
        
        # Direct action indicators
        if any(indicator in sentence_lower for indicator in action_indicators):
            return True
        
        # Check for imperative mood (commands)
        if doc and len(doc) > 0:
            first_token = doc[0]
            # Commands often start with base form verbs
            if first_token.pos_ == 'VERB' and first_token.tag_ == 'VB':
                return True
        
        # Check for future tense constructions
        for i, token in enumerate(doc):
            if token.text.lower() == 'will' and i + 1 < len(doc):
                next_token = doc[i + 1]
                if next_token.pos_ == 'VERB':
                    return True
        
        # Check for modal verbs indicating obligation
        modal_obligations = ['should', 'must', 'need', 'have']
        for token in doc:
            if token.text.lower() in modal_obligations and token.pos_ in ['VERB', 'AUX']:
                return True
        
        # Check for person names followed by action verbs (assignments)
        for i, token in enumerate(doc):
            if token.ent_type_ == 'PERSON' and i + 1 < len(doc):
                next_token = doc[i + 1]
                if next_token.text.lower() in ['will', 'should', 'must', 'to']:
                    return True
        
        return False

    def analyze_with_patterns(self, text: str) -> Dict[str, List[str]]:
        """Fallback pattern-based analysis when Spacy is not available"""
        results = {"actions": [], "decisions": [], "questions": []}
        
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check for questions first (highest priority)
            if self._check_patterns(line, self.question_patterns):
                results["questions"].append(line)
            # Then decisions
            elif self._check_patterns(line, self.decision_patterns):
                results["decisions"].append(line)
            # Finally actions
            elif self._check_patterns(line, self.action_patterns):
                results["actions"].append(line)
        
        return results

    def _check_patterns(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any of the given patterns"""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False


class MeetingNotesApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Meeting Notes Analyzer")
        self.root.geometry("1000x700")
        
        self.analyzer = MeetingNotesAnalyzer()
        self.dark_mode = False
        
        self.setup_styles()
        self.create_widgets()
        self.apply_theme()
        
    def setup_styles(self):
        self.style = ttk.Style()
        
        # Light theme colors
        self.light_colors = {
            'bg': '#ffffff',
            'fg': '#000000',
            'select_bg': '#0078d4',
            'select_fg': '#ffffff',
            'frame_bg': '#f0f0f0',
            'button_bg': '#e1e1e1',
            'entry_bg': '#ffffff'
        }
        
        # Dark theme colors
        self.dark_colors = {
            'bg': '#2d2d2d',
            'fg': '#ffffff',
            'select_bg': '#404040',
            'select_fg': '#ffffff',
            'frame_bg': '#404040',
            'button_bg': '#404040',
            'entry_bg': '#404040'
        }
    
    def create_widgets(self):
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Title and controls
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        title_frame.columnconfigure(1, weight=1)
        
        ttk.Label(title_frame, text="Meeting Notes Analyzer", 
                 font=("Arial", 16, "bold")).grid(row=0, column=0, sticky=tk.W)
        
        # Dark mode toggle
        self.dark_mode_var = tk.BooleanVar()
        ttk.Checkbutton(title_frame, text="Dark Mode", 
                       variable=self.dark_mode_var,
                       command=self.toggle_dark_mode).grid(row=0, column=2, sticky=tk.E)
        
        # Input section
        input_frame = ttk.LabelFrame(main_frame, text="Input", padding="5")
        input_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        
        # File upload section
        controls_frame = ttk.Frame(input_frame)
        controls_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        ttk.Button(controls_frame, text="📁 Upload File", 
                  command=self.upload_file).pack(side=tk.LEFT, padx=(0, 10))
        
        # Show NLP method being used
        method_text = "🔍 Using: Spacy NLP" if SPACY_AVAILABLE else "⚠️ Using: Pattern Matching (Install Spacy for better results)"
        ttk.Label(controls_frame, text=method_text, 
                 foreground="green" if SPACY_AVAILABLE else "orange").pack(side=tk.LEFT)
        
        # Text input
        self.text_input = scrolledtext.ScrolledText(input_frame, height=8, wrap=tk.WORD)
        self.text_input.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        
        # Process button
        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=2, column=0, pady=(5, 0))
        
        ttk.Button(button_frame, text="🔍 Analyze Notes", 
                  command=self.analyze_notes).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="📄 Export Results", 
                  command=self.export_results).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="🗑️ Clear All", 
                  command=self.clear_all).pack(side=tk.LEFT)
        
        # Results section
        results_frame = ttk.Frame(main_frame)
        results_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        results_frame.columnconfigure(0, weight=1)
        results_frame.columnconfigure(1, weight=1)
        results_frame.columnconfigure(2, weight=1)
        results_frame.rowconfigure(0, weight=1)
        
        # Action Items
        action_frame = ttk.LabelFrame(results_frame, text="🎯 Action Items", padding="5")
        action_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        action_frame.columnconfigure(0, weight=1)
        action_frame.rowconfigure(0, weight=1)
        
        self.action_text = scrolledtext.ScrolledText(action_frame, height=15, wrap=tk.WORD)
        self.action_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Decisions
        decision_frame = ttk.LabelFrame(results_frame, text="📌 Decisions Made", padding="5")
        decision_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        decision_frame.columnconfigure(0, weight=1)
        decision_frame.rowconfigure(0, weight=1)
        
        self.decision_text = scrolledtext.ScrolledText(decision_frame, height=15, wrap=tk.WORD)
        self.decision_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Questions
        question_frame = ttk.LabelFrame(results_frame, text="❓ Open Questions", padding="5")
        question_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        question_frame.columnconfigure(0, weight=1)
        question_frame.rowconfigure(0, weight=1)
        
        self.question_text = scrolledtext.ScrolledText(question_frame, height=15, wrap=tk.WORD)
        self.question_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready - Paste your meeting notes above and click 'Analyze Notes'")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
    
    def apply_theme(self):
        colors = self.dark_colors if self.dark_mode else self.light_colors
        
        # Configure root window
        self.root.configure(bg=colors['bg'])
        
        # Configure text widgets
        for widget in [self.text_input, self.action_text, self.decision_text, self.question_text]:
            widget.configure(
                bg=colors['entry_bg'],
                fg=colors['fg'],
                selectbackground=colors['select_bg'],
                selectforeground=colors['select_fg'],
                insertbackground=colors['fg']
            )
    
    def toggle_dark_mode(self):
        self.dark_mode = self.dark_mode_var.get()
        self.apply_theme()
    
    def upload_file(self):
        file_types = [("Text files", "*.txt")]
        if DOCX_AVAILABLE:
            file_types.append(("Word documents", "*.docx"))
        file_types.append(("All files", "*.*"))
        
        filename = filedialog.askopenfilename(
            title="Select meeting notes file",
            filetypes=file_types
        )
        
        if filename:
            try:
                if filename.endswith('.docx') and DOCX_AVAILABLE:
                    doc = docx.Document(filename)
                    text = '\n'.join([paragraph.text for paragraph in doc.paragraphs])
                else:
                    with open(filename, 'r', encoding='utf-8') as file:
                        text = file.read()
                
                self.text_input.delete(1.0, tk.END)
                self.text_input.insert(1.0, text)
                self.status_var.set(f"Loaded: {os.path.basename(filename)}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Could not load file: {str(e)}")
    
    def highlight_keywords(self, text_widget, content: str, keywords: List[str]):
        """Add keyword highlighting to text"""
        text_widget.delete(1.0, tk.END)
        text_widget.insert(1.0, content)
        
        # Configure highlighting tags
        if self.dark_mode:
            text_widget.tag_configure("keyword", foreground="#66b3ff", font=("Arial", 9, "bold"))
            text_widget.tag_configure("bullet", foreground="#ffcc66")
        else:
            text_widget.tag_configure("keyword", foreground="#0066cc", font=("Arial", 9, "bold"))
            text_widget.tag_configure("bullet", foreground="#ff6600")
        
        # Highlight keywords
        for keyword in keywords:
            start_pos = '1.0'
            while True:
                pos = text_widget.search(keyword, start_pos, stopindex=tk.END, nocase=True)
                if not pos:
                    break
                end_pos = f"{pos}+{len(keyword)}c"
                text_widget.tag_add("keyword", pos, end_pos)
                start_pos = end_pos
        
        # Highlight bullet points
        start_pos = '1.0'
        while True:
            pos = text_widget.search("•", start_pos, stopindex=tk.END)
            if not pos:
                break
            end_pos = f"{pos}+1c"
            text_widget.tag_add("bullet", pos, end_pos)
            start_pos = end_pos
    
    def display_results(self, results: Dict[str, List[str]]):
        """Display analysis results with keyword highlighting"""
        action_keywords = ["will", "should", "must", "need to", "action", "task", "todo", "assign", "responsible"]
        decision_keywords = ["decided", "agreed", "resolved", "concluded", "decision", "approved", "confirmed"]
        question_keywords = ["what", "how", "when", "where", "why", "who", "question", "unclear", "unsure"]
        
        # Display actions
        actions = results.get("actions", [])
        if actions:
            actions_content = "\n\n".join([f"• {action}" for action in actions])
        else:
            actions_content = "No action items found in the meeting notes."
        self.highlight_keywords(self.action_text, actions_content, action_keywords)
        
        # Display decisions
        decisions = results.get("decisions", [])
        if decisions:
            decisions_content = "\n\n".join([f"• {decision}" for decision in decisions])
        else:
            decisions_content = "No decisions found in the meeting notes."
        self.highlight_keywords(self.decision_text, decisions_content, decision_keywords)
        
        # Display questions
        questions = results.get("questions", [])
        if questions:
            questions_content = "\n\n".join([f"• {question}" for question in questions])
        else:
            questions_content = "No open questions found in the meeting notes."
        self.highlight_keywords(self.question_text, questions_content, question_keywords)
    
    def analyze_notes(self):
        text = self.text_input.get(1.0, tk.END).strip()
        if not text:
            messagebox.showwarning("Warning", "Please enter some meeting notes first.")
            return
        
        self.status_var.set("Analyzing meeting notes...")
        self.root.update()
        
        def analyze_thread():
            try:
                results = self.analyzer.analyze_with_spacy(text)
                self.root.after(0, lambda: self.finish_analysis(results))
            except Exception as e:
                self.root.after(0, lambda: self.analysis_error(str(e)))
        
        threading.Thread(target=analyze_thread, daemon=True).start()
    
    def finish_analysis(self, results: Dict[str, List[str]]):
        self.display_results(results)
        self.current_results = results
        
        # Count results
        total_actions = len(results.get("actions", []))
        total_decisions = len(results.get("decisions", []))
        total_questions = len(results.get("questions", []))
        
        method = "Spacy" if SPACY_AVAILABLE else "Pattern Matching"
        self.status_var.set(f"Analysis complete using {method} - Found: {total_actions} actions, {total_decisions} decisions, {total_questions} questions")
    
    def analysis_error(self, error_msg: str):
        self.status_var.set("Analysis failed - check your input and try again")
        messagebox.showerror("Error", f"Analysis failed: {error_msg}")
    
    def clear_all(self):
        """Clear all input and results"""
        self.text_input.delete(1.0, tk.END)
        self.action_text.delete(1.0, tk.END)
        self.decision_text.delete(1.0, tk.END)
        self.question_text.delete(1.0, tk.END)
        self.status_var.set("Ready - All content cleared")
        if hasattr(self, 'current_results'):
            delattr(self, 'current_results')
    
    def export_results(self):
        if not hasattr(self, 'current_results'):
            messagebox.showwarning("Warning", "No analysis results to export. Please analyze some notes first.")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="Save analysis results"
        )
        
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as file:
                    file.write("MEETING NOTES ANALYSIS REPORT\n")
                    file.write("=" * 50 + "\n")
                    file.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    file.write(f"Analysis Method: {'Spacy NLP' if SPACY_AVAILABLE else 'Pattern Matching'}\n\n")
                    
                    # Action Items
                    actions = self.current_results.get("actions", [])
                    file.write("🎯 ACTION ITEMS:\n")
                    file.write("-" * 30 + "\n")
                    if actions:
                        for i, action in enumerate(actions, 1):
                            file.write(f"{i}. {action}\n")
                    else:
                        file.write("No action items found.\n")
                    file.write("\n")
                    
                    # Decisions
                    decisions = self.current_results.get("decisions", [])
                    file.write("📌 DECISIONS MADE:\n")
                    file.write("-" * 30 + "\n")
                    if decisions:
                        for i, decision in enumerate(decisions, 1):
                            file.write(f"{i}. {decision}\n")
                    else:
                        file.write("No decisions found.\n")
                    file.write("\n")
                    
                    # Questions
                    questions = self.current_results.get("questions", [])
                    file.write("❓ OPEN QUESTIONS:\n")
                    file.write("-" * 30 + "\n")
                    if questions:
                        for i, question in enumerate(questions, 1):
                            file.write(f"{i}. {question}\n")
                    else:
                        file.write("No open questions found.\n")
                    
                    # Summary
                    file.write("\n" + "=" * 50 + "\n")
                    file.write("SUMMARY:\n")
                    file.write(f"Total Action Items: {len(actions)}\n")
                    file.write(f"Total Decisions: {len(decisions)}\n")
                    file.write(f"Total Open Questions: {len(questions)}\n")
                
                self.status_var.set(f"Results exported to: {os.path.basename(filename)}")
                messagebox.showinfo("Success", f"Results exported successfully to:\n{filename}")
                
            except Exception as e:
                messagebox.showerror("Error", f"Could not export results: {str(e)}")


def main():
    root = tk.Tk()
    app = MeetingNotesApp(root)
    
    # Show installation instructions if Spacy is not available
    if not SPACY_AVAILABLE:
        info_msg = ("Spacy NLP library not found!\n\n"
                   "For best results, install Spacy:\n"
                   "1. pip install spacy\n"
                   "2. python -m spacy download en_core_web_sm\n\n"
                   "The app will work with basic pattern matching for now.")
        messagebox.showinfo("Installation Recommendation", info_msg)
    
    if not DOCX_AVAILABLE:
        print("Note: python-docx not installed. Install it to support .docx files: pip install python-docx")
    
    root.mainloop()


if __name__ == "__main__":
    main()