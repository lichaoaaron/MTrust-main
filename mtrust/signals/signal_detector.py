class SignalDetector:

    def __init__(self, config):
        self.signals = config["signals"]

    def detect(self, text):
        score = 0.0

        for signal in self.signals:
            for pattern in signal["patterns"]:
                if pattern in text:
                    score += signal["weight"]

        return {"score": min(score, 1.0)}