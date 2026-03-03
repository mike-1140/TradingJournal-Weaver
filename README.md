Projekt: Trading Journal 3.0
Es ist ein Journal um meine Trades abzubilden und auszuwerten.
Das Projekt besteht aus mehreren Teilen:
-- import_ibkr_trades:
Tägliche bekomme ich von IBKR FlexQuery-Dateien, Protokoll der letzten 30 Tage (XML-Datei).
Diese Dateien werden analysiert und die Daten in eine MYSQL-Datenbank geschrieben werden (Table: TRADES_RAW).
In der MYSQL-Datei entsteht dadurch eine chronische Reihenfolge.
-- aggregate_ibkr_trades_raw:
Manche Orders bestehen aus mehreren Teil-Trades. Dieser aggregiert die Daten aus
der Tabelle TRADES_RAW und schreibt die Daten (alle auch die nicht aggregierten) in
eine neue Tabelle (TRADES_RAW_AGGR). Die zeitliche Reihenfolge bleibt erhalten.
-- process_ibkr_trades:
Dieser Teil geht die Tabelle TRADES_RAW_AGGR zeilenweise (in der zeitlichen Reihenfolge)
durch und bearbeitet jeden einzelnen Trade. Es werden die Tabellen TRADE_OPEN und TRADE_CLOSE
geschrieben und aktualisiert.
