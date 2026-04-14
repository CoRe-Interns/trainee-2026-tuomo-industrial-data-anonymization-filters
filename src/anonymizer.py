from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

class AnonymizerTool:
    def __init__(self, entities, threshold):
        # Initialize Presidio engines
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        self.entities = entities
        self.threshold = threshold

    def process_text(self, text):
        # 1. Analyze text and find data to anonymize
        results = self.analyzer.analyze(
            text=text, 
            entities=self.entities, 
            language='en', 
            score_threshold=self.threshold
        )
        
        # 2. Anonymize findings (replace them with tags like [PERSON])
        anonymized_result = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results
        )
        
        return anonymized_result.text, results