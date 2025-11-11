let VAR_1 = 0;
let VAR_2 = [];
while (VAR_2.length < 10000) VAR_2.push(VAR_2.length);
for (const VAR_3 in VAR_2) {
  if (VAR_2.hasOwnProperty(VAR_3)) {
    VAR_1 += VAR_2[VAR_3];
  }
}
