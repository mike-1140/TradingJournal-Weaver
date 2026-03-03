# src/logger/emoji_log.py

class EmojiLog:
    def __init__(self, logger):
        self.logger = logger

    # --- CORE ---
    def info(self, msg): self.logger.info(msg)
    def warn(self, msg): self.logger.warning(msg)
    def error(self, msg): self.logger.error(msg)
    def debug(self, msg): self.logger.debug(msg)

    # --- TRADING ---
    def trade(self, msg): self.logger.info(f"🟢 {msg}")
    def option(self, msg): self.logger.info(f"🟦 {msg}")
    def future(self, msg): self.logger.info(f"🟥 {msg}")
    def equity(self, msg): self.logger.info(f"🟩 {msg}")

    # --- CASH / FINANCE ---
    def cash(self, msg): self.logger.info(f"💰 {msg}")
    def fx(self, msg): self.logger.info(f"💱 {msg}")
    def dividend(self, msg): self.logger.info(f"🪙 {msg}")
    def corp(self, msg): self.logger.info(f"🏦 {msg}")

    # --- XML / PARSER ---
    def xml(self, msg): self.logger.info(f"📄 {msg}")
    def clean(self, msg): self.logger.debug(f"🧹 {msg}")

    # --- DB / ETL ---
    def db(self, msg): self.logger.info(f"💾 {msg}")
    def insert(self, msg): self.logger.info(f"➕ {msg}")
    def update(self, msg): self.logger.info(f"🔄 {msg}")
    def batch(self, msg): self.logger.debug(f"📦 {msg}")
    def dup(self, msg): self.logger.warning(f"🧱 {msg}")

    # --- SYSTEM / CORE ---
    def start(self, msg): self.logger.info(f"🚀 {msg}")
    def stop(self, msg): self.logger.info(f"🛑 {msg}")
    def ok(self, msg): self.logger.info(f"✔️ {msg}")
    def warn_core(self, msg): self.logger.warning(f"⚠️ {msg}")
    def fail(self, msg): self.logger.error(f"❌ {msg}")
    def crit(self, msg): self.logger.critical(f"💥 {msg}")

