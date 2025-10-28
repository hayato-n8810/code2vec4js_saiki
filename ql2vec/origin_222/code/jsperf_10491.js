Array.prototype.FUNCTION_1 = function () {};
Object.prototype.FUNCTION_2 = function () {};
var VAR_1 = ["allo", "bonjour", "test"];
VAR_1.FUNCTION_3 = function () {};
function FUNCTION_4(VAR_2) {}
for (var VAR_3 in VAR_1) {
  if (VAR_1.hasOwnProperty(VAR_3)) FUNCTION_4(VAR_3);
}
