"use client";

import { Tab, TabGroup, TabList, TabPanel, TabPanels } from "@headlessui/react";
import { cn } from "@/app/_lib/utils";

type TabsProps = Omit<React.ComponentProps<typeof TabGroup>, "children"> & {
  className?: string;
  defaultIndex?: number;
  children?: React.ReactNode;
};

function Tabs({ className, children, defaultIndex, ...props }: TabsProps) {
  return (
    <TabGroup defaultIndex={defaultIndex} {...props}>
      <div className={cn("flex flex-col gap-2", className)} data-slot="tabs">
        {children}
      </div>
    </TabGroup>
  );
}

function TabsList({
  className,
  children,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <TabList
      className={cn(
        "bg-muted text-muted-foreground inline-flex h-9 w-fit items-center justify-center rounded-lg p-[3px]",
        className
      )}
      data-slot="tabs-list"
      {...props}
    >
      {children}
    </TabList>
  );
}

function TabsTrigger({
  className,
  children,
  ...props
}: React.ComponentProps<"button">) {
  return (
    <Tab
      className={({ selected }: { selected: boolean }) =>
        cn(
          "inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-md border border-transparent px-2 py-1 text-sm font-medium whitespace-nowrap transition-[color,box-shadow] focus-visible:ring-[3px] focus-visible:outline-1 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
          selected
            ? "bg-background shadow-sm text-foreground"
            : "text-foreground",
          className
        )
      }
      data-slot="tabs-trigger"
      {...props}
    >
      {children}
    </Tab>
  );
}

function TabsPanels({
  className,
  children,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <TabPanels className={className} {...props}>
      {children}
    </TabPanels>
  );
}

function TabsContent({
  className,
  children,
  value: _value,
  ...props
}: React.ComponentProps<"div"> & { value?: string }) {
  return (
    <TabPanel
      className={cn("flex-1 outline-none", className)}
      data-slot="tabs-content"
      {...props}
    >
      {children}
    </TabPanel>
  );
}

export { Tabs, TabsList, TabsTrigger, TabsPanels, TabsContent };
