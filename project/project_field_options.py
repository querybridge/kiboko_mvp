locations = (
		('Header', 'Header'),
		('Footer', 'Footer'),
		('Home Page', 'Home Page'),
		('Category Page', 'Category Page'),
		('Product List Page', 'Product List Page'),
		('Product Detail Page', 'Product Detail Page'),
		('Cart Page', 'Cart Page'),
		('Order Tracking Page', 'Order Tracking Page'),
		('Landing Page', 'Landing Page'),
	)

# Status == the Kanban column an action sits in (see services/kanban.py), plus
# the two terminal states that live in the Archive rather than on the board.
status_options = (
		('Incomplete Entry', 'Incomplete Entry'),
		('Ready to Score', 'Ready to Score'),
		('Scored', 'Scored'),
		('On Deck', 'On Deck'),
		('WIP', 'WIP'),
		('Blocked', 'Blocked'),
		('Complete', 'Complete'),
		('Launched', 'Launched'),
	)

STRATEGY_TAG_CHOICES = (
	('', '---------'),
	('Expand Selection', 'Expand Selection'),
	('Improve Experience', 'Improve Experience'),
	('Increase Urgency', 'Increase Urgency'),
	('Top of Mind', 'Top of Mind'),
)

# AEE (Attract / Engage / Expand) alignment for an Action.
AEE_ALIGNMENT_CHOICES = (
	('', '---------'),
	('attract_traffic', 'Attract Traffic'),
	('engage_customers', 'Engage Customers'),
	('expand_purchase', 'Expand Purchase'),
)
