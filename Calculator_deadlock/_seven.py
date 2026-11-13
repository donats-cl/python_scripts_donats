import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler

X = np.array([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]).reshape(-1, 1)
y = np.array([5.83, 6.11, 6.37, 6.61, 6.83, 7.03, 7.21, 7.38, 7.54, 7.69, 7.83])

s = StandardScaler()
X = s.fit_transform(X)

m = LinearRegression()
m.fit(X, y)
y_pred = m.predict(X)

r2 = r2_score(y, y_pred)
mae = mean_absolute_error(y, y_pred)
coef = m.coef_[0]
inter = m.intercept_

print(f"y = {coef:.4f} * x + {inter:.4f}")
print(f"Коффіцієнт детермінації R²: {r2:.4f}")
print(f"MAE: {mae:.4f}")

print(f"Аналіз: (Коффіцієнт {coef:.4f} < 0).")

pred = lambda x: m.predict(s.transform(np.array([x]).reshape(-1,1)))

y_real = np.array([7.96])
y_test = pred(110)

print(f"110 = {y_real}, {y_test=}, {y_real/y_test}, {r2_score(y_real, y_test)}, {mean_absolute_error(y_real, y_test)}")
