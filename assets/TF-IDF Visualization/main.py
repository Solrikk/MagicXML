import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import PCA
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.pyplot as plt
from matplotlib import colors
from matplotlib import cm

documents = [
    "Services", "Furniture", "Cottage and garden", "Home and Decor",
    "Lighting", "Plumbing", "Renovation and finishing", "Appliances",
    "Payment of debt", "Products without a category", "1+1=discount",
    "Plumbing///Water supply", "Lighting///Chandeliers", "Lighting///Fixtures",
    "Lighting///Sconces and lights", "Lighting///Table lamps",
    "Lighting///Floor lamps", "Lighting///Spots", "Lighting///Track systems",
    "Lighting///Office lighting", "Lighting///Street lighting",
    "Lighting///LED backlight", "Lighting///Light bulbs",
    "Lighting///Accessories", "Home and Decor///Bedding",
    "Home and Decor///Bed linen", "Home and Decor///Tableware",
    "Home and Decor///Organization and storage", "Home and Decor///Textile",
    "Home and Decor///Household goods", "Home and decor///Covers"
]

documents.append("Furniture///Sofa")

vectorizer = TfidfVectorizer()
X = vectorizer.fit_transform(documents)

pca = PCA(n_components=3)
data_3d = pca.fit_transform(X.toarray())

fig = plt.figure()
ax = fig.add_subplot(111, projection='3d')

norm = colors.Normalize(data_3d[:, 0].min(), data_3d[:, 0].max())
cmap = cm.viridis
m = cm.ScalarMappable(norm=norm, cmap=cmap)

xs = data_3d[:, 0]
ys = data_3d[:, 1]
zs = data_3d[:, 2]
cs = m.to_rgba(data_3d[:, 0])

sizes = (np.sqrt(xs**2 + ys**2 + zs**2) * 80)

ax.scatter(xs, ys, zs, color=cs, s=sizes)

ax.scatter(xs[-1], ys[-1], zs[-1], color='red', s=sizes[-1], label='Sofa')
ax.legend()

ax.set_title('Enhanced Categories Insight')
ax.set_xlabel('Primary Variation Direction')
ax.set_ylabel('Secondary Variation Direction')
ax.set_zlabel('Tertiary Variation Direction')

cbar = plt.colorbar(m, ax=ax)
cbar.set_label('Intensity of Primary Variation Direction')

plt.show()
