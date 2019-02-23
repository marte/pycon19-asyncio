from collections import namedtuple
import asyncio
import random
import enum
import time


class Event(enum.Enum):
    ENTER = enum.auto()
    ORDER = enum.auto()
    READY = enum.auto()
    LEAVE = enum.auto()
    
Dish = namedtuple("Dish", "name cooking_time")

class Restaurant:
    def __init__(self, menu, num_tables):
        self.menu = menu
        
        self._tables = [False] * num_tables
        self._waiting_customers = []
        
        self._orders = [None] * num_tables
        self._ordered_dishes = []
        self._ordered_dishes_cond = asyncio.Condition()
        self._ready_dishes = []
        
        self._events_queue = asyncio.Queue()
        
    async def enter(self):
        fut = asyncio.get_running_loop().create_future()
        self._events_queue.put_nowait((Event.ENTER, fut))
        return await fut
    
    def order_food(self, table_id, dishes):
        dish_events = []
        orders = []
        for dish in dishes:
            dish_event = asyncio.Event()
            orders.append((dish, dish_event))
        self._orders[table_id] = orders
        # Call waiter and place the orders.
        self._events_queue.put_nowait((Event.ORDER, table_id))
        
    async def wait_for_food(self, table_id):
        # Wait for ALL the dishes to be delivered.
        orders = self._orders[table_id]
        for dish, dish_event in orders:
            await dish_event.wait()
    
    def leave(self, table_id):
        # Leave the table.
        self._tables[table_id] = False
        self._events_queue.put_nowait((Event.LEAVE,))

    async def waiter(self, waiter_id):
        while True:
            event = await self._events_queue.get()
            if event[0] == Event.ENTER:
                # Attempt to seat a new customer.
                for table_id, occupied in enumerate(self._tables):
                    if not occupied:
                        # Table found!
                        self._tables[table_id] = True
                        event[1].set_result(table_id)
                        break
                else:
                    # No available table, make them wait.
                    self._waiting_customers.append(event[1])
                await asyncio.sleep(1)
            elif event[0] == Event.ORDER:
                # Take orders.
                table_id = event[1]
                # Queue the orders for the cooks.
                async with self._ordered_dishes_cond:
                    for dish, dish_event in self._orders[table_id]:
                        self._ordered_dishes.append((table_id, dish))
                    self._ordered_dishes_cond.notify_all()
                await asyncio.sleep(2)
            elif event[0] == Event.READY:
                # Deliver food.
                table_id, dish = self._ready_dishes.pop(0)
                for dish, dish_event in self._orders[table_id]:
                    dish_event.set()
                await asyncio.sleep(3)
            elif event[0] == Event.LEAVE:
                if not self._waiting_customers:
                    continue
                # Seat a waiting customer.
                for table_id, occupied in enumerate(self._tables):
                    if not occupied:
                        self._tables[table_id] = True
                        self._waiting_customers.pop(0).set_result(table_id)
                        break
                await asyncio.sleep(1)


    async def cook(self, cook_id):
        while True:
            async with self._ordered_dishes_cond:
                # Wait for orders.
                await self._ordered_dishes_cond.wait_for(lambda: len(self._ordered_dishes) > 0)
                # There can be different strategies for cooking. This one is just FIFO (first in, first out).
                table_id, dish = self._ordered_dishes.pop(0)
            await asyncio.sleep(dish.cooking_time)
            self._ready_dishes.append((table_id, dish))
            self._events_queue.put_nowait((Event.READY,))

async def customer(customer_id, restaurant):
    print(f"Customer {customer_id} enters")
    t = time.time()
    table_id = await restaurant.enter()
    print(f"Customer {customer_id} is seated at Table {table_id} (waited for {time.time() - t:.0f}min)")
    
    num_dishes = random.randint(1, 3)
    dishes = random.sample(restaurant.menu, num_dishes)
    dish_names = ", ".join(dish.name for dish in dishes)
    print(f"Customer {customer_id} orders {dish_names}")
    restaurant.order_food(table_id, dishes)
    
    t = time.time()
    await restaurant.wait_for_food(table_id)
    
    print(f"Customer {customer_id} is ready to eat (waited for {time.time() - t:.0f}min)")
    # Eat.
    await asyncio.sleep(num_dishes * 10)
    
    restaurant.leave(table_id)
    print(f"Customer {customer_id} leaves")


async def simulate(restaurant, num_waiters, num_cooks, customer_rate):
    for waiter_id in range(num_waiters):
        asyncio.create_task(restaurant.waiter(waiter_id))
    for cook_id in range(num_cooks):
        asyncio.create_task(restaurant.cook(cook_id))
    num_customers = 0
    while True:
        num_customers += 1
        asyncio.create_task(customer(num_customers, restaurant))
        await asyncio.sleep(1.0 / customer_rate)
