# Attribute-Listen aus deinem XML
trade_fields = {
    "accountId", "acctAlias", "model", "currency", "fxRateToBase",
    "assetCategory", "subCategory", "symbol", "description", "conid",
    "securityID", "securityIDType", "cusip", "isin", "figi", "listingExchange",
    "underlyingConid", "underlyingSymbol", "underlyingSecurityID",
    "underlyingListingExchange", "issuer", "issuerCountryCode",
    "tradeID", "multiplier", "relatedTradeID", "strike", "reportDate",
    "expiry", "dateTime", "putCall", "tradeDate", "principalAdjustFactor",
    "settleDateTarget", "transactionType", "exchange", "quantity",
    "tradePrice", "tradeMoney", "proceeds", "taxes", "ibCommission",
    "ibCommissionCurrency", "netCash", "closePrice", "openCloseIndicator",
    "notes", "cost", "fifoPnlRealized", "mtmPnl", "origTradePrice",
    "origTradeDate", "origTradeID", "origOrderID", "origTransactionID",
    "buySell", "clearingFirmID", "ibOrderID", "transactionID", "ibExecID",
    "relatedTransactionID", "rtn", "brokerageOrderID", "orderReference",
    "volatilityOrderLink", "exchOrderId", "extExecID", "orderTime",
    "openDateTime", "holdingPeriodDateTime", "whenRealized",
    "whenReopened", "levelOfDetail", "changeInPrice", "changeInQuantity",
    "orderType", "traderID", "isAPIOrder", "accruedInt", "initialInvestment",
    "serialNumber", "deliveryType", "commodityType", "fineness", "weight",
    "positionActionID"
}

optioneae_fields = {
    "accountId", "acctAlias", "model", "currency", "fxRateToBase",
    "assetCategory", "subCategory", "symbol", "description", "conid",
    "securityID", "securityIDType", "cusip", "isin", "figi", "listingExchange",
    "underlyingConid", "underlyingSymbol", "underlyingSecurityID",
    "underlyingListingExchange", "issuer", "issuerCountryCode",
    "multiplier", "strike", "expiry", "putCall", "principalAdjustFactor",
    "date", "transactionType", "quantity", "tradePrice", "markPrice",
    "proceeds", "commisionsAndTax", "costBasis", "realizedPnl",
    "fxPnl", "mtmPnl", "tradeID", "serialNumber", "deliveryType",
    "commodityType", "fineness", "weight"
}

corporate_fields = {
    "accountId", "acctAlias", "model", "currency", "fxRateToBase",
    "assetCategory", "subCategory", "symbol", "description", "conid",
    "securityID", "securityIDType", "cusip", "isin", "figi",
    "listingExchange", "underlyingConid", "underlyingSymbol",
    "underlyingSecurityID", "underlyingListingExchange", "issuer",
    "issuerCountryCode", "multiplier", "strike", "expiry", "putCall",
    "principalAdjustFactor", "reportDate", "dateTime",
    "actionDescription", "amount", "proceeds", "value", "quantity",
    "fifoPnlRealized", "mtmPnl", "code", "type", "transactionID",
    "actionID", "levelOfDetail", "serialNumber", "deliveryType",
    "commodityType", "fineness", "weight"
}

# Schnittmengen & Differenzen
# common = trade_fields & optioneae_fields
# only_trade = trade_fields - optioneae_fields
# only_optioneae = optioneae_fields - trade_fields
#
# print("Gemeinsame Felder:", sorted(common))
# print("\nNur in Trade:", sorted(only_trade))
# print("\nNur in OptionEAE:", sorted(only_optioneae))
